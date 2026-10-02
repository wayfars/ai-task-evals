import importlib.util
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ai_eval", ROOT / "src" / "ai_eval.py")
ai_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ai_eval
SPEC.loader.exec_module(ai_eval)


class EvaluationContractTests(unittest.TestCase):
    def test_fixture_has_40_unique_cases_with_balanced_development_and_heldout(self):
        cases = json.loads((ROOT / "fixtures" / "tasks.json").read_text())
        self.assertEqual(len(cases), 40)
        self.assertEqual(len({c["case_id"] for c in cases}), 40)
        self.assertEqual(sum(c["split"] == "development" for c in cases), 20)
        self.assertEqual(sum(c["split"] == "heldout" for c in cases), 20)

    def test_grader_checks_required_and_unexpected_fields(self):
        case = {"expected": {"answer": "42", "evidence_id": "A"}}
        self.assertTrue(ai_eval.grade(case, '{"answer":"42","evidence_id":"A"}')['accepted'])
        result = ai_eval.grade(case, '{"answer":"42","evidence_id":"A","extra":true}')
        self.assertFalse(result['accepted'])
        self.assertEqual(result['extra_count'], 1)

    def test_invalid_answer_is_a_semantic_failure_not_an_infrastructure_failure(self):
        result = ai_eval.grade({"expected": {"answer": "x"}}, "not json")
        self.assertEqual(result['outcome'], 'invalid-json')

    def test_json_grading_rejects_boolean_for_number_duplicate_keys_and_nan(self):
        case = {"expected": {"count": 1}}
        self.assertEqual(ai_eval.grade(case, '{"count":true}')['outcome'], 'wrong-answer')
        self.assertEqual(ai_eval.grade({"expected": {"items": [1]}},
                                       '{"items":[true]}')['outcome'], 'wrong-answer')
        self.assertEqual(ai_eval.grade(case, '{"count":1,"count":1}')['outcome'], 'invalid-json')
        self.assertEqual(ai_eval.grade(case, '{"count":NaN}')['outcome'], 'invalid-json')

    def test_scored_rows_do_not_echo_untrusted_keys_or_invalid_response_text(self):
        case = {"case_id": "synthetic-1", "split": "development",
                "category": "test", "prompt": "synthetic", "expected": {"answer": "ok"}}
        raw_answers = [
            '{"answer":"ok","confidential_response_field":"CONFIDENTIAL_RESPONSE_SENTINEL"}',
            '{"answer":"ok","confidential_duplicate_field":"first",'
            '"confidential_duplicate_field":"CONFIDENTIAL_RESPONSE_SENTINEL"}',
        ]
        for raw in raw_answers:
            with self.subTest(raw=raw), patch.object(ai_eval, "endpoint_answer",
                                                     return_value=(raw, 0.001)):
                rows, _ = ai_eval.run([case], mock=False,
                                      base_url="http://example.invalid/v1",
                                      model="synthetic", timeout=1)
                serialized = json.dumps(rows)
                self.assertNotIn("confidential_", serialized)
                self.assertNotIn("CONFIDENTIAL_RESPONSE_SENTINEL", serialized)

    def test_output_contract_is_answer_independent_and_enums_include_distractors(self):
        first = {"expected": {"action": "write_recovery_handoff", "evidence_id": None}}
        changed = {"expected": {"action": "pause", "evidence_id": "B"}}
        contract = ai_eval.output_contract(first)
        self.assertEqual(contract, ai_eval.output_contract(changed))
        schema = json.loads(contract.rsplit("\n", 1)[-1])
        self.assertEqual(schema["properties"]["evidence_id"]["type"], ["string", "null"])
        action_values = schema["properties"]["action"]["enum"]
        self.assertGreater(len(action_values), 1)
        self.assertIn("write_recovery_handoff", action_values)
        self.assertIn("pause", action_values)
        self.assertIn("continue", action_values)
        self.assertNotIn("enum", schema["properties"]["evidence_id"])

    def test_all_declared_enum_vocabularies_have_more_than_one_answer_independent_choice(self):
        self.assertTrue(ai_eval.ENUMS)
        self.assertTrue(all(len(set(values)) > 1 for values in ai_eval.ENUMS.values()))
        cases = ai_eval.load_cases(ROOT / "fixtures" / "tasks.json", "all")
        for case in cases:
            schema = json.loads(ai_eval.output_contract(case).rsplit("\n", 1)[-1])
            for field, value in case["expected"].items():
                if field in ai_eval.ENUMS:
                    self.assertIn(value, schema["properties"][field]["enum"])

    def test_fixture_enum_order_is_canonical_and_expected_answers_are_not_first_cues(self):
        cases = ai_eval.load_cases(ROOT / "fixtures" / "tasks.json", "all")
        enum_count = 0
        expected_at_zero = 0
        positions = set()
        for case in cases:
            original_contract = ai_eval.output_contract(case)
            schema = json.loads(original_contract.rsplit("\n", 1)[-1])
            for field, expected in case["expected"].items():
                if field not in ai_eval.ENUMS:
                    continue
                choices = schema["properties"][field]["enum"]
                self.assertEqual(choices, sorted(set(choices)))
                position = choices.index(expected)
                positions.add(position)
                enum_count += 1
                expected_at_zero += position == 0

                changed = copy.deepcopy(case)
                changed["expected"][field] = choices[(position + 1) % len(choices)]
                self.assertEqual(original_contract, ai_eval.output_contract(changed))
        self.assertEqual(enum_count, 44)
        self.assertGreater(len(positions), 1)
        self.assertLess(expected_at_zero, enum_count // 2,
                        "expected enum labels appear first too often")

    def test_invalid_split_fails_fixture_load_instead_of_silently_disappearing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "cases.json"
            fixture.write_text(json.dumps([{
                "case_id": "bad", "split": "typo", "category": "x",
                "prompt": "prompt", "expected": {"answer": "x"},
            }]))
            with self.assertRaisesRegex(ValueError, "invalid split"):
                ai_eval.load_cases(fixture, "development")

    def test_endpoint_rejects_truncated_and_null_choice_responses(self):
        class Response:
            def __init__(self, body):
                self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _limit=None): return json.dumps(self.body).encode()

        for body in (
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            {"choices": [{"finish_reason": None, "message": {"content": "{}"}}]},
            {"choices": [{"finish_reason": "content_filter", "message": {"content": "{}"}}]},
            {"choices": None},
            {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
        ):
            with self.subTest(body=body), patch.object(ai_eval.urllib.request, "urlopen",
                                                     return_value=Response(body)):
                with self.assertRaises(ai_eval.EndpointProtocolError):
                    ai_eval.endpoint_answer("http://example.invalid/v1", "m", "p", 1)

    def test_timeouts_and_output_limits_are_finite_and_bounded(self):
        for timeout in (0, float("inf"), float("nan"), ai_eval.MAX_TIMEOUT_S + 1):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                ai_eval.endpoint_answer("http://example.invalid/v1", "m", "p", timeout)
        for limit in (0, True, ai_eval.MAX_OUTPUT_TOKENS + 1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ai_eval.endpoint_answer("http://example.invalid/v1", "m", "p", 1, limit)

    def test_live_request_sets_output_cap_and_limits_response_read(self):
        class Response:
            read_limit = None
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, limit=None):
                self.read_limit = limit
                return json.dumps({"choices": [{"finish_reason": "stop",
                                                 "message": {"content": "{}"}}]}).encode()

        response = Response()
        request = []
        with patch.object(ai_eval.urllib.request, "urlopen",
                          side_effect=lambda req, timeout: (request.append(req) or response)):
            answer, _ = ai_eval.endpoint_answer("http://example.invalid/v1", "m", "p", 1, 17)
        payload = json.loads(request[0].data)
        self.assertEqual(answer, "{}")
        self.assertEqual(payload["max_tokens"], 17)
        self.assertEqual(response.read_limit, ai_eval.MAX_RESPONSE_BYTES + 1)

    def test_mock_adapter_runs_without_network_or_model(self):
        cases = ai_eval.load_cases(ROOT / "fixtures" / "tasks.json", "heldout")
        rows, code = ai_eval.run(cases, mock=True, base_url=None, model=None, timeout=1)
        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(row['accepted'] for row in rows))
        self.assertTrue(all(row['answer_sha256'] for row in rows))

    def test_aggregate_keeps_task_coverage_and_infrastructure_count_visible(self):
        report = ai_eval.summarize([
            {"split": "development", "category": "x", "accepted": True,
             "elapsed_s": 1.0, "infrastructure_failure": False},
            {"split": "development", "category": "x", "accepted": False,
             "elapsed_s": 2.0, "infrastructure_failure": True},
        ])
        self.assertEqual(report['development/x']['attempts'], 2)
        self.assertEqual(report['development/x']['infrastructure_failures'], 1)


if __name__ == "__main__":
    unittest.main()
