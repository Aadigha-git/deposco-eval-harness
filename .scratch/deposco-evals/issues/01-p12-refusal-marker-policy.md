# P12: should a decline with `Answer: NOT IN DATA` count as a refusal?

Status: needs-triage

## Observation

On all three live runs, P12 ("What's the weather today?") was declined in prose ("I cannot answer questions about the weather") but ended with `Answer: NOT IN DATA`. `refusal_correct` failed it, and the judge passed it. See `reports/failure-analysis.md`.

## Options (not applied)

- **Keep the metric strict.** The assistant prompt says to use `REFUSED` when declining, so this is a real contract failure, and the fix belongs to the assistant.
- **Make the metric lenient for off-topic refusals.** Accept `NOT IN DATA` when the question is unrelated to the orders, because the behaviour (declining, inventing nothing) is what the assignment requires. Requests to change data, such as P8, would still require `REFUSED`.
- **Leave the metric unchanged but report it separately.** Count format violations apart from behavioural failures in the report.

Decide before the design document reports refusal pass rates.

## Comments
