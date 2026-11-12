# Judge rubric: is a per-item count the CSV contradicts a FAIL?

Status: needs-triage

## Observation

On C2 for 11-17, the reply said "Cedar Lane Books: 2 (orders 1062, 1077)", but the CSV has three cancelled orders for that customer (1062, 1077, 1111). That dropped a tied winner. The judge returned PASS, because the rubric says not to check arithmetic or fail a reply only because a number is wrong. Calibration example cal-01 sits on the same boundary.

## Proposal (not applied)

Clarify the rubric as follows. Totals and the final answer are out of scope, but a per-item fact the reply states about the data is graded as grounding. Examples are "customer X has 2 cancelled orders" or "order 1076 is not UPS".

Before changing anything:
- have a human relabel cal-01 and add a C2-style example to a second calibration round
- re-run calibration once

## Comments
