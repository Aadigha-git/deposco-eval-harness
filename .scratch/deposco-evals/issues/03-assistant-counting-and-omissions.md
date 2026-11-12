# Assistant counting, summing, and row omissions

Status: needs-triage

## Observation

The live runs found these assistant errors:
- **Off-by-one counts:** P1 on all three files.
- **Wrong sums over a correct list:** P9 on 11-10 and P5 on 11-17.
- **Omitted rows:** P4 on 11-10 (order 1076) and C2 on 11-17 (order 1111).
- **The wrong date column:** P10 on 11-10.

The deterministic metrics catch every value error. The judge can't see omissions, because a missing row isn't an unsupported claim.

## Proposals (not applied; the assistant must not be tuned against these runs before the design document records them)

- **Assistant:** try a prompt that asks for a numbered list of matching rows before the total, or move counting and summing to code with the LLM only phrasing the answer. Measure on a new snapshot, not on these three files.
- **Evaluator:** optionally add a deterministic check that every expected evidence order ID appears in the reply, for cases that list rows. Only add it if the design document argues for it, since it grades the explanation's completeness, not the answer.
- **Measurement:** re-run each file once more to estimate how much of this is run-to-run variation.

## Comments
