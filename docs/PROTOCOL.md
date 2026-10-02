# Evaluation protocol v1

## Question and scope

The first battery checks whether a model can follow fixed evidence and
operational rules in four narrow categories: retrieval, agent lifecycle,
evaluation design, and local inference operations. It is a harness demonstration
and task battery, not a broad capability benchmark.

## Cases and split

There are 40 distinct synthetic cases, ten per category. The first five in each
category are development cases and the last five are designated held-out cases.
The answer key is public alongside the prompts, so the held-out labels are not
secret. Do not tune against this set and then present it as an independent blind
test. For a blind comparison, freeze the evaluator and create a fresh sealed set.

## Request contract

Each request uses temperature 0 and asks for a JSON object. The runner appends
an explicit per-case output contract: exact required keys, JSON value types,
and canonical labels for enum fields. The expected answer is not sent to the
endpoint. The grader requires exact recursive JSON equality and rejects missing
or extra fields, duplicate keys, non-standard constants, and type substitutions
(for example, `true` where the answer key contains `1`). Invalid answers are
semantic failures. Network, timeout, truncation, and endpoint response-shape
failures are recorded as infrastructure failures and are not silently dropped.
The request caps generated output at a configurable token count (default 2,048,
maximum 8,192), response bodies at one megabyte, and request timeouts at one
hour. A completion is accepted for grading only when `finish_reason` is `stop`.
Scored rows retain only an answer hash and safe grading counts; arbitrary keys
and response text are not copied into reports.

The local mock adapter returns the expected JSON solely to verify fixture
loading, grading, split selection, and report generation. It provides no
evidence about model performance.

## Measurements and limits

The runner reports acceptance counts and rates, elapsed request time, and
infrastructure failures by split and category. It records fixture and evaluator
SHA-256 hashes. It does not estimate significance, causal effects, cost,
concurrent throughput, energy, or human review burden. One case is one distinct
task; repeated trials must remain visible as repeated attempts and should not
be described as new tasks.

The correct response to infrastructure failure is to fix or disclose the
infrastructure issue and rerun under the same frozen protocol. Do not relabel a
timeout as a semantic model failure. The runner stores answer hashes but omits
raw answer text to reduce accidental transcript retention.

## Live endpoint safety

No live request occurs without `--live`, `--base-url`, and `--model`. A live run
is an explicit user action. The runner makes ordinary chat-completions requests
only; it does not install models, switch services, edit routing, or execute
returned code. A configured endpoint may still log its own requests, so use
synthetic prompts and a trusted endpoint.
