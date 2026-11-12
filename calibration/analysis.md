# Judge calibration analysis

Run analysed: `calibration/predictions.json` and `calibration/report.md`. It used `gemini-3.8-flash`, made one call per example with no retries, and ran at 2026-11-12T18:25:18Z.

## Provenance

- `calibration/labels.json` was first added in commit `d7bd05b`, and no commit has touched it since.
- `deposco_evals/judge.py` first appears in `dafc920`, a descendant of `d7bd05b`.
- The rubric was clarified once, in `dafc920`, from code review and before any judge run. All 10 human verdicts were re-checked then and none changed.
- The run's rubric and labels hashes are recorded in the report.

## Result

| Measure | Result |
|---|---|
| Exact agreement | 10 of 10 |
| PASS versus not-PASS | 10 of 10 |
| Per class | PASS 3/3, FLAG 2/2, FAIL 5/5 |
| Judge errors | 0 |

Every evidence quote the judge gave (8 items) appears verbatim in the reply or the CSV. The two FLAG verdicts gave no evidence, which the rubric allows.

## Disagreements

None. There is therefore nothing to classify as rubric ambiguity, judge inconsistency, or a possible human-label issue for this run.

## What this agreement does not show

- **The set is easy.**
  - Seven of the ten replies are hand-written with one clear violation or none.
  - Only cal-01 (a self-contradictory count) and cal-10 (a vague but correct explanation) are borderline.
  - 10 of 10 on this set is weak evidence about harder replies.
- **cal-01 agreed for a narrow reason, which points to possible rubric ambiguity.**
  - The judge's reason praises the filter and the listed IDs, and never mentions that the reply says "7 orders" while listing 8.
  - That matches the clarified rubric, which says not to fail or flag a wrong number.
  - Whether the original wording would have produced FLAG was never tested, because the rubric was clarified before the first run.
  - The boundary between "wrong arithmetic" and "a fact the CSV contradicts" depends entirely on that one rubric sentence.
- **Judge consistency is unmeasured.** Each example was judged once, so run-to-run variation at temperature 0 is unknown.
- **Possible human-label issue for the whole set: the labels were written by the coding agent, not by an independent human.**
  - The agent also wrote the rubric, so the labels and the rubric share one author's reading.
  - Agreement may partly reflect that shared reading.
  - A person other than the rubric author should confirm or relabel the 10 examples.
- **Coverage gaps** (also listed in the spec):
  - no not-in-data case (P7, P11), ties case (C2) or date-boundary case (C3)
  - no reply that refuses an answerable question
  - no hand-written PASS

## Proposed changes (not applied)

1. **Labels:** have an independent human confirm or relabel the 10 examples before the agreement figure is used in the design document. If any verdict changes, record it as a new commit and re-run the judge once.
2. **Labels:** a future second calibration round should add harder cases, kept separate from this run's labels so this result stays reproducible. Candidates:
   - a refusal of an answerable question, which should FAIL
   - a not-in-data reply that invents a count, which should FAIL
   - an honest "not in the data" reply, which should PASS
   - a C2 reply that names only one of two tied customers while explaining the filter correctly (the rubric would say PASS; the answer metric catches the miss)
   - a reply that states "this month" as 2026-11-01 to 2026-11-03, a partial range that covers all the data, as a likely FLAG or PASS borderline
3. **Rubric:** if the human review disagrees on cal-01, consider stating explicitly how to treat a reply that contradicts itself on a count. Don't change it until a human label says the current wording is wrong.
4. **Judge consistency:** in a later slice, re-judge the same examples once more and report how many verdicts changed, as a separate measurement from agreement.
