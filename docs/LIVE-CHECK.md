# Live development check

A single frozen 40-case run against an OpenAI-compatible local endpoint accepted 26/40 answers under the strict structured rubric: 14/20 development and 12/20 held-out-designated cases. There were no infrastructure failures. Incorrect answers remain in the denominator and scored rows. The output contract uses canonical enum vocabularies independent of each expected answer, including label order.

This exercises the live evaluator, bounded completions, strict grading, and failure reporting. It is not an independent model ranking. The case answer key is public, the split is not blind, the endpoint was shared with simultaneous inference smoke work, and hardware, weights, runtime commit, cache state, and background load were not pinned. Timing is descriptive. Temperature was 0, the output cap 512 tokens, and request timeout 30 seconds.

[Machine-readable results](live-development-results.json) retain safe scores, answer hashes, source hashes, and the configured request settings. Raw answers were not retained, so these automated decisions have not received independent semantic adjudication. The strict rubric can reject plausible paraphrases or alternate interpretations. New controlled studies should use newly authored sealed cases, frozen protocols, repeated paired trials, and independent review.
