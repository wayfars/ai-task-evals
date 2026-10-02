# AI Task Evaluations

A small, reproducible harness for comparing model behavior on synthetic agent,
retrieval, evaluation-design, and inference-operations tasks. The initial suite
contains 40 distinct cases: 20 development and 20 held-out. Scores are strict
structured-answer checks with explicit required fields, JSON types, and
canonical label vocabularies for enum fields. The grader rejects duplicate
keys, non-standard JSON constants, and type substitutions. The tool records
latency, split/category coverage,
infrastructure failures, and hashes of the evaluator and fixture; it never
stores raw model responses.

The bundled mock adapter proves the grading and reporting path without making
network or model calls:

```sh
python3 src/ai_eval.py --mock --split all
```

Run the tests with:

```sh
python3 -m unittest discover -s tests -v
```

An explicit live run uses an OpenAI-compatible endpoint. It is opt-in, and it
does not change production routing or services:

```sh
python3 src/ai_eval.py --live --base-url http://127.0.0.1:8080/v1 \
  --model example-model --split development --output results/run.jsonl
```

Set `AI_EVAL_API_KEY` only when the chosen endpoint requires it. Result files
contain scores, timing, error class, and an answer hash, never the answer text.
The API key is read from the environment and is not printed or saved.
Live generation is bounded by `--max-output-tokens` (default 2,048; maximum
8,192), a one-megabyte response-body cap, and a finite timeout of at most one
hour. The evaluator grades only complete responses with `finish_reason: stop`.

## Interpretation

The answer key is shipped with the public fixture, so anyone can inspect it.
“Held-out” here means the split designated for evaluation after prompt or
configuration development; it is not a blind set once this repository is
public. Do not use these public cases to claim independent, statistically
powered model rankings. For selection work, prepare a new private holdout or
rotate in newly authored cases after freezing the evaluation protocol.

The suite measures compliance with these specific synthetic tasks. It does not
measure open-ended coding quality, safety in deployment, or general retrieval
quality. Exact JSON matching is intentionally strict and should be reported as
such. Repeated attempts on one case do not increase the number of distinct
tasks. Mock results are plumbing checks, not model evidence.

See [the protocol](docs/PROTOCOL.md) and [case inventory](docs/CASE-INVENTORY.md)
for the rules and split manifest. See the [release inventory and provenance
notes](docs/release-inventory.md) for artifact boundaries and the
[historical routing pilot](docs/historical-routing-case-study.md) for a separate,
small negative result that this suite does not reproduce.

## Related portfolio

See [the portfolio map](PORTFOLIO.md) for related application, evaluation, inference, and agent operations projects.

## Live development evidence

A [40-case live development check](docs/LIVE-CHECK.md) reports strict accepted and rejected outcomes with explicit limits. It is separate from the mock adapter and historical routing pilot.
