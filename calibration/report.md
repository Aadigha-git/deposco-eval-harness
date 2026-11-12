# Judge calibration report

- Judge model: gemini-3.8-flash
- Run at: 2026-11-12T18:25:18+00:00 (one judge call per example, no retries)
- Rubric: `deposco_evals/judge_rubric.md` (sha256 `f00a9f4c12a9`)
- Labels: `calibration/labels.json` (sha256 `9d1e37d2c108`)
- Verdicts are categorical: FLAG is its own class, never partial credit.

## Agreement

Exact: the judge's verdict equals the human verdict on **10 of 10** examples (100%).

PASS versus not-PASS: **10 of 10** examples (100%), with FLAG and FAIL both counted as not-PASS.

## Confusion matrix

Rows are the human verdict, columns the judge verdict.

| human \ judge | PASS | FLAG | FAIL |
|---|---|---|---|
| **PASS** | 3 | 0 | 0 |
| **FLAG** | 0 | 2 | 0 |
| **FAIL** | 0 | 0 | 5 |

Judge errors (outside the matrix): 0

## Per-class agreement

Of the examples a human labelled with each verdict, how many the judge matched. Judge errors count as misses.

| Human verdict | Judge agreed | Agreement |
|---|---|---|
| PASS | 3 of 3 | 100% |
| FLAG | 2 of 2 | 100% |
| FAIL | 5 of 5 | 100% |

## Disagreements

None.
