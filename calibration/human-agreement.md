# Human review of the judge calibration set

The candidate reviewed the same 10 calibration replies in [`human-review.md`](human-review.md). The worksheet showed each question, reply, the reference date, the relevant CSV rows, and the judge rubric. It omitted the earlier labels, the judge's verdicts, and the agreement results, and it presented the examples in shuffled order. Nothing was re-run: the judge's verdicts are the saved ones in [`predictions.json`](predictions.json), from one call per example with `gemini-3.8-flash`.

## Candidate versus Gemini judge

- Exact agreement: **10 of 10**.
- PASS versus not-PASS: **10 of 10**.
- Per class: PASS 3/3, FLAG 2/2, FAIL 5/5.
- Disagreements: none.

| candidate \ judge | PASS | FLAG | FAIL |
|---|---|---|---|
| **PASS** | 3 | 0 | 0 |
| **FLAG** | 0 | 2 | 0 |
| **FAIL** | 0 | 0 | 5 |

The candidate's verdicts also match the earlier labels in [`labels.json`](labels.json) (written by the AI coding agent) on all 10 examples.

## How far this goes

- **The review was not fully blind.** Before the worksheet was completed, conversation summaries had already mentioned several of the agent's labels and the 10/10 judge result. The worksheet hid them, but the candidate may have recalled them.
- **The set is easy.** Seven of the ten replies are hand-written with one clear violation or none, and each was judged once.
- **Coverage is incomplete.** No example covers ties, not-in-data, date boundaries, or refusing an answerable question.

This confirms that a human reads the rubric the same way as the judge on clear-cut cases. It is not strong evidence of judge reliability on harder replies. A second, fully blind round on harder examples would be the next step; see [`analysis.md`](analysis.md).
