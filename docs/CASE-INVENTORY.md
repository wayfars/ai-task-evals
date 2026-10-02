# Case inventory

Each category has five development cases and five held-out-designated cases.
The public answer key means the latter are not blind after publication.

| Category | Development IDs | Held-out-designated IDs | Focus |
|---|---|---|---|
| Retrieval | ret-01–ret-05 | ret-06–ret-10 | Source selection, abstention, dates, and evidence IDs |
| Lifecycle | lif-01–lif-05 | lif-06–lif-10 | Handoffs, bounded retries, human pause, and verification |
| Evaluation | eva-01–eva-05 | eva-06–eva-10 | Independent tasks, leakage, failures, confounding, and uncertainty |
| Inference | inf-01–inf-05 | inf-06–inf-10 | End-to-end latency, reproducibility, readiness, and resource tradeoffs |

All case evidence is synthetic. Cases specify expected structured fields and
are scored by exact equality. A pass means only that the response matched this
case's expected fields.
