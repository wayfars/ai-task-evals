#!/usr/bin/env python3
"""Run a small, controlled task set against a mock or explicit chat endpoint."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "fixtures" / "tasks.json"
MAX_TIMEOUT_S = 3600
MAX_OUTPUT_TOKENS = 8192
DEFAULT_OUTPUT_TOKENS = 2048
MAX_RESPONSE_BYTES = 1_000_000

ENUMS = {
    "action": ["write_recovery_handoff", "retry_with_skeleton_handoff", "pause",
               "remain_paused", "preserve_context_and_escalate", "handoff_and_stop",
               "disable_or_investigate_before_claiming_speedup", "abort_benchmark",
               "continue", "resume", "investigate", "ask_human", "retry_with_budget",
               "record_failure", "reconfigure", "stop"],
    "status": ["not_verified", "accomplished", "not_engaged", "paused", "running",
               "verified", "complete", "blocked", "unknown", "ready"],
    "liveness": ["unknown", "alive", "idle", "dead", "degraded"],
    "resume_mode": ["resume", "restart", "new_session"],
    "context_source": ["saved_handoff", "fresh_context", "prior_transcript"],
    "terminal_state": ["accomplished", "paused", "running", "failed"],
    "outcome": ["infrastructure_failure", "semantic_failure", "accepted", "invalid_json"],
    "evaluation_type": ["matched_offline_replay", "live_comparison", "benchmark"],
    "bias_risk": ["selection_on_observed_results", "sampling_bias", "order_effect"],
    "validity": ["invalid_for_blind_evaluation", "valid_for_blind_evaluation", "limited"],
    "primary_issue": ["answer_leakage", "sampling_bias", "implementation_bug"],
    "current_role": ["development_set", "heldout_set", "test_set"],
    "decision": ["reject_under_current_rule", "accept", "defer"],
    "basis": ["severe_defect_veto", "average_score", "insufficient_evidence"],
    "risk": ["order_and_cache_confounding", "selection_bias", "measurement_noise"],
    "mitigation": ["randomize_or_block_and_report_order", "increase sample size", "none"],
    "metric_status": ["biased", "unbiased", "unknown"],
    "correction": ["include_all_attempts_and_separate_infrastructure_failures",
                   "drop failures", "retry only failures"],
    "conclusion": ["no_failures_observed_in_this_sample",
                   "higher_decode_rate_did_not_make_this_task_faster",
                   "failure_rate_is_zero", "performance_improved"],
    "uncertainty": ["sample_is_too_small_to_estimate_rare_failure_rate",
                    "precisely estimated", "no uncertainty"],
    "metric": ["end_to_end_latency", "decode_rate", "time_to_first_token"],
    "experiment_quality": ["confounded", "controlled", "inconclusive"],
    "readiness": ["unproven", "ready", "unavailable"],
    "next_action": ["record_probe_failure_and_do_not_route_work", "route work", "restart service"],
    "claim": ["single_client_result_only", "general throughput result", "production ready"],
    "missing_measurement": ["concurrent_aggregate_throughput", "latency", "memory use"],
    "suitability": ["not_acceptable_for_this_task", "acceptable", "unknown"],
    "joint_measurement": ["quality_and_resource_cost", "quality only", "resource cost only"],
    "reproducibility": ["insufficient", "reproducible", "partially reproducible"],
    "report_quality": ["incomplete", "complete", "misleading"],
    "required_handling": ["include_timeouts_as_failures_and_report_separately",
                          "omit timeouts", "retry until success"],
    "inference": ["repeats_are_not_distinct_tasks", "repeats are independent tasks",
                  "repeats increase sample size"],
    "comparison": ["tie_on_observed_cases", "model A wins", "model B wins"],
    "limitation": ["ceiling_effect_prevents_quality_discrimination",
                   "sample is representative", "no limitation"],
    "fix": ["change_one_factor_per_comparison", "increase sample size",
            "repeat the same run"],
}

FIELD_TYPES = {
    "action": "string", "accepted": "boolean", "answer": "string",
    "authorized": "boolean", "basis": "string", "bias_risk": "string",
    "claim": "string", "claim_complete": "boolean", "comparison": "string",
    "completed_items": "array", "conclusion": "string", "context_source": "string",
    "correction": "string", "current_role": "string", "decision": "string",
    "evidence_id": ["string", "null"], "experiment_quality": "string",
    "failure_count": "integer", "fix": "string", "inference": "string", "independent_tasks": "integer",
    "joint_measurement": "string", "limitation": "string", "liveness": "string",
    "metric": "string", "metric_status": "string", "missing_fields": "array",
    "missing_measurement": "string", "mitigation": "string", "next_action": "string",
    "next_step": "string", "outcome": "string", "primary_issue": "string",
    "readiness": "string", "reason": "string", "reproducibility": "string",
    "report_quality": "string", "required_handling": "string", "resume_mode": "string",
    "retries": "integer", "risk": "string", "status": "string",
    "suitability": "string", "terminal_state": "string", "uncertainty": "string",
    "validity": "string", "evaluation_type": "string", "cold_load_s": "integer",
    "warm_request_s": "integer", "launch_another_session": "boolean",
    "requires_human": "boolean",
}


class EndpointProtocolError(ValueError):
    """The endpoint returned a response that cannot be graded reliably."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"non-standard JSON constant: {value}")


def _json_type(value) -> str:
    # bool is a subclass of int in Python, but JSON booleans are not numbers.
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _strict_equal(left, right) -> bool:
    if _json_type(left) != _json_type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_strict_equal(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def parse_answer(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    value = json.loads(text, object_pairs_hook=_unique_object,
                       parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError("answer must be a JSON object")
    return value


def grade(case: dict, raw: str) -> dict:
    try:
        parsed = parse_answer(raw)
    except json.JSONDecodeError:
        return {"accepted": False, "outcome": "invalid-json", "detail": "malformed JSON"}
    except ValueError as exc:
        detail = "answer must be a JSON object" if str(exc) == "answer must be a JSON object" else "invalid JSON structure"
        return {"accepted": False, "outcome": "invalid-json", "detail": detail}
    expected = case["expected"]
    missing = sorted(set(expected) - set(parsed))
    wrong = sorted(k for k, value in expected.items()
                   if k in parsed and not _strict_equal(parsed[k], value))
    extra = sorted(set(parsed) - set(expected))
    accepted = not (missing or wrong or extra)
    return {"accepted": accepted, "outcome": "accepted" if accepted else "wrong-answer",
            "missing": missing, "wrong": wrong, "extra_count": len(extra)}


def mock_answer(case: dict) -> str:
    """Deterministic adapter used to exercise plumbing without a model."""
    return json.dumps(case["expected"], sort_keys=True)


def output_contract(case: dict) -> str:
    """Build a target-independent contract from the declared output field names.

    Field types and enum vocabularies are evaluator metadata, never inferred
    from the answer key. Free-text string fields are scored by strict lexical
    equality; they are not presented as enums.
    """
    keys = sorted(case["expected"])
    properties = {}
    for key in keys:
        if key not in FIELD_TYPES:
            raise ValueError(f"no declared output schema for field: {key}")
        field_type = FIELD_TYPES[key]
        item = {"type": field_type}
        if key in ENUMS:
            # Canonical sort is independent of the answer-key choice: never put
            # the expected label first as a hidden cue to the model.
            item["enum"] = sorted(ENUMS[key])
        properties[key] = item
    schema = {"type": "object", "properties": properties,
              "required": keys, "additionalProperties": False}
    return ("\n\nOutput contract (follow exactly): return one JSON object with exactly "
            "the required keys below; each value must have the stated JSON type. "
            "For any enum field, use one of its listed canonical values.\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True))


def endpoint_answer(base_url: str, model: str, prompt: str, timeout: float,
                    max_output_tokens: int = DEFAULT_OUTPUT_TOKENS) -> tuple[str, float]:
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT_S:
        raise ValueError(f"timeout must be finite and in (0, {MAX_TIMEOUT_S}] seconds")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_output_tokens must be an integer in [1, {MAX_OUTPUT_TOKENS}]")
    payload = {"model": model, "temperature": 0, "max_tokens": max_output_tokens,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content":
                             "Return only one JSON object matching the requested schema."},
                            {"role": "user", "content": prompt}]}
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("AI_EVAL_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers,
                                 method="POST")
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        try:
            body_bytes = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body_bytes) > MAX_RESPONSE_BYTES:
                raise EndpointProtocolError("response exceeds maximum size")
            body = json.loads(body_bytes, object_pairs_hook=_unique_object,
                              parse_constant=_reject_constant)
        except EndpointProtocolError:
            raise
        except (json.JSONDecodeError, ValueError) as exc:
            raise EndpointProtocolError("response is not strict JSON") from exc
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        raise EndpointProtocolError("response has no choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise EndpointProtocolError("choice is not an object")
    if choice.get("finish_reason") != "stop":
        raise EndpointProtocolError("response did not finish normally")
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise EndpointProtocolError("response content is missing or not text")
    return content, time.monotonic() - start


def load_cases(path: Path, split: str) -> list[dict]:
    cases = json.loads(path.read_text())
    if not isinstance(cases, list):
        raise ValueError("fixture root must be a JSON array")
    ids = set()
    selected = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        for field in ("case_id", "split", "category", "prompt", "expected"):
            if field not in case:
                raise ValueError(f"case missing {field}")
        if not isinstance(case["case_id"], str) or not case["case_id"].strip():
            raise ValueError("case_id must be a nonempty string")
        if case["split"] not in ("development", "heldout"):
            raise ValueError(f"invalid split for {case['case_id']}: {case['split']!r}")
        if not isinstance(case["category"], str) or not case["category"].strip():
            raise ValueError(f"invalid category for {case['case_id']}")
        if not isinstance(case["prompt"], str) or not isinstance(case["expected"], dict) or not case["expected"]:
            raise ValueError(f"invalid prompt or expected object for {case['case_id']}")
        for key, value in case["expected"].items():
            if key not in FIELD_TYPES:
                raise ValueError(f"no declared output schema for field: {key}")
            allowed_types = FIELD_TYPES[key]
            if _json_type(value) not in (allowed_types if isinstance(allowed_types, list)
                                         else [allowed_types]):
                raise ValueError(f"wrong expected JSON type for {case['case_id']}.{key}")
            if key in ENUMS and value not in ENUMS[key]:
                raise ValueError(f"unknown canonical enum for {case['case_id']}.{key}")
        if case["case_id"] in ids:
            raise ValueError(f"duplicate case_id: {case['case_id']}")
        ids.add(case["case_id"])
        if case["split"] in ("development", "heldout") and (split == "all" or split == case["split"]):
            selected.append(case)
    if not selected:
        raise ValueError("no cases selected")
    return selected


def summarize(rows: list[dict]) -> dict:
    groups = {}
    for row in rows:
        key = (row["split"], row["category"])
        groups.setdefault(key, []).append(row)
    return {f"{split}/{category}": {
        "attempts": len(items), "accepted": sum(r["accepted"] for r in items),
        "acceptance_rate": sum(r["accepted"] for r in items) / len(items),
        "mean_elapsed_s": statistics.mean(r["elapsed_s"] for r in items),
        "infrastructure_failures": sum(r["infrastructure_failure"] for r in items),
    } for (split, category), items in sorted(groups.items())}


def run(cases: list[dict], *, mock: bool, base_url: str | None, model: str | None,
        timeout: float, max_output_tokens: int = DEFAULT_OUTPUT_TOKENS) -> tuple[list[dict], int]:
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_TIMEOUT_S:
        raise ValueError(f"timeout must be finite and in (0, {MAX_TIMEOUT_S}] seconds")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_output_tokens must be an integer in [1, {MAX_OUTPUT_TOKENS}]")
    rows = []
    exit_code = 0
    for case in cases:
        infrastructure_failure = False
        start = time.monotonic()
        try:
            if mock:
                answer = mock_answer(case)
                elapsed = time.monotonic() - start
            else:
                answer, elapsed = endpoint_answer(
                    base_url, model, case["prompt"] + output_contract(case), timeout,
                    max_output_tokens)
        except (OSError, TimeoutError, urllib.error.URLError, KeyError,
                json.JSONDecodeError, EndpointProtocolError) as exc:
            infrastructure_failure = True
            answer = ""
            elapsed = time.monotonic() - start
            result = {"accepted": False, "outcome": "infrastructure-failure",
                      "detail": type(exc).__name__}
            exit_code = 2
        else:
            result = grade(case, answer)
        rows.append({"case_id": case["case_id"], "split": case["split"],
                     "category": case["category"], "model": model or "mock",
                     "accepted": result["accepted"], "outcome": result["outcome"],
                     "elapsed_s": round(elapsed, 6),
                     "infrastructure_failure": infrastructure_failure,
                     "answer_sha256": hashlib.sha256(answer.encode()).hexdigest() if answer else None,
                     "grade": {k: v for k, v in result.items() if k not in ("accepted", "outcome")}})
    return rows, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--split", choices=("development", "heldout", "all"), default="development")
    parser.add_argument("--mock", action="store_true", help="offline deterministic adapter; makes no model calls")
    parser.add_argument("--live", action="store_true", help="explicitly enable an OpenAI-compatible endpoint")
    parser.add_argument("--base-url", help="endpoint base URL, for example http://127.0.0.1:8080/v1")
    parser.add_argument("--model", help="explicit endpoint model name")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_OUTPUT_TOKENS,
                        help=f"endpoint output limit (1-{MAX_OUTPUT_TOKENS}; default {DEFAULT_OUTPUT_TOKENS})")
    parser.add_argument("--output", type=Path, help="write scored JSONL; raw model text is never saved")
    args = parser.parse_args()
    if args.mock == args.live:
        parser.error("choose exactly one of --mock or --live")
    if args.live and (not args.base_url or not args.model):
        parser.error("--live requires both --base-url and --model")
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= MAX_TIMEOUT_S:
        parser.error(f"--timeout must be finite and in (0, {MAX_TIMEOUT_S}]")
    if not 1 <= args.max_output_tokens <= MAX_OUTPUT_TOKENS:
        parser.error(f"--max-output-tokens must be in [1, {MAX_OUTPUT_TOKENS}]")
    cases = load_cases(args.cases, args.split)
    rows, code = run(cases, mock=args.mock, base_url=args.base_url,
                     model=args.model, timeout=args.timeout,
                     max_output_tokens=args.max_output_tokens)
    report = {"protocol": "ai-task-evals/v1", "split": args.split,
              "adapter": "mock" if args.mock else "chat-completions",
              "model": args.model or "mock",
              "case_count": len(cases), "results": summarize(rows),
              "fixture_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "note": "Descriptive scores only. This rubric does not establish general model quality."}
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
