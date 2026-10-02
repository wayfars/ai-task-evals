# Release inventory and provenance

This snapshot contains the evaluator CLI, a 40-case synthetic JSON fixture,
model-free evaluator tests, protocol and case-inventory documentation, this
historical pilot summary, an MIT license, and a CI workflow. It contains no
model weights, private model registry, credentials, production request logs,
or raw historical transcripts.

The synthetic fixture has 20 development cases and 20 held-out-designated
cases. Its answer key is public. The held-out label records intended use during
development; it does not describe a blind or contamination-proof test today.
The cases are microtasks, not a repository-level software engineering
benchmark.

The historical routing pilot in
[historical-routing-case-study.md](historical-routing-case-study.md) is a
separate, narrow empirical report. Its source run did not pin the runner,
runtime build, and model weights as a reproducible package, so this snapshot
does not claim to recreate it. The report is intentionally limited to the
recorded counts, observed timings, and stated caveats.

For a new harness run, the JSON report records the SHA-256 hashes of the exact
fixture and evaluator source used. Those hashes identify those two input files;
they do not pin an endpoint, its model weights, its server build, or external
request handling. Mock scores verify only fixture loading, grading, and report
generation.

The reviewed live development report contains only synthetic task identifiers, strict grading diagnostics, answer hashes, and selected run metadata. It omits endpoint addresses, credentials, and raw model responses.
