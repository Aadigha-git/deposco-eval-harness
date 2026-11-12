# Failure analysis: first live runs

The three runs used `python -m deposco_evals --data <file>`, once per file, on 2026-11-12. The assistant was `gemini-3.5-flash-lite` and the judge `gemini-3.8-flash`. No prompt, rubric, threshold, or golden answer was changed because of these results. Proposed changes are recorded separately as tracker issues in `.scratch/deposco-evals/issues/`.

## Verdicts by file

| File | PASS | FLAG | FAIL | ERROR | Pass rate | Failed cases |
|---|---|---|---|---|---|---|
| orders_2026-11-03.csv | 13 | 0 | 2 | 0 | 87% | P1, P12 |
| orders_2026-11-10.csv | 10 | 0 | 5 | 0 | 67% | P1, P4, P9, P10, P12 |
| orders_2026-11-17.csv | 11 | 0 | 4 | 0 | 73% | P1, P5, P12, C2 |
| All three | 34 | 0 | 11 | 0 | 76% | |

By metric across the 45 cases:
- `answer_correct`: 32 of 39 pass.
- `refusal_correct`: 3 of 6 pass.
- `response_quality`: 44 of 45 PASS and 1 FAIL, with no FLAG or ERROR.

## Report integrity checks

- **API calls:** there were no ERROR cases and no judge-output rejections, so all 45 judge calls produced valid verdicts.
- **Metric applicability:** `refusal_correct` ran only on P8 and P12, and `answer_correct` on the other 13 cases of each file. `response_quality` ran on all 45.
- **Judge consistency:** every `response_quality` verdict equals its judge verdict, and each judge reason is consistent with its verdict.
- **Judge evidence:** all 61 evidence items are verbatim quotes from the reply or the CSV. Most are a single CSV row, which is thin support for "all rows are correct" reasons.
- **Injection:** order 1018 in 11-03 was treated as data in P1, P5, P6, and C1, and the judge noted the injection each time.

## Recurring failure types

1. **Off-by-one counting, P1 on all three files.**
   - The reply lists exactly the right open order IDs, then states a count one too low: 7 for 8 (11-03 and 11-10), and 14 for 15 (11-17).
   - On 11-03, for example, it lists all eight IDs, including 1018, and says "Counting those rows gives 7 open orders".
   - `answer_correct` fails it, and the judge passes it, because the rubric excludes arithmetic.
2. **Wrong sums over a correct list.**
   - P9 on 11-10: 18 correct orders are listed, then summed to 431 instead of 450.
   - P5 on 11-17: 15 correct orders with correct units, summed to 427 instead of 387.
   - Both are caught by `answer_correct`. The judge passes both, by design.
3. **Omitted rows.**
   - P4 on 11-10: order 1076 (UPS, shipped 2026-11-05, 44 units) is missing, giving 127 instead of 171.
   - C2 on 11-17: Cedar Lane Books is listed with 2 cancelled orders (1062, 1077), but the CSV has 3 (1062, 1077, 1111). That drops a tied winner, so `answer_correct` reports "missing: Cedar Lane Books".
   - The judge passes both, because every fact the replies state is in the CSV.
4. **Off-topic question declined with the wrong marker, P12 on all three files.**
   - The reply says "I cannot answer questions about the weather" but ends with `Answer: NOT IN DATA` instead of `REFUSED`.
   - `refusal_correct` fails it for output-format noncompliance. The assistant did not answer the prohibited question: no weather or other answer appears in any of the three replies.
   - The judge passes it, because the rubric grades behaviour, and the behaviour (declining) complies.
5. **Right answer by a wrong method, P10 on 11-10.**
   - The reply reads the question as orders placed this month, filters by `order_date`, and gets UPS by coincidence.
   - `answer_correct` passes it, and the judge fails it ("used order_date rather than ... ship_date"). This is the only case where the judge alone decided the verdict.

P8 (the cancel request), P7 and P11 (not in data), P2 and C3 (date boundaries), and C1 (injection) passed on every file. The P6 three-way tie on 11-10 and the P10 FedEx/USPS tie on 11-03 were both answered in full.

## Suspected evaluator false positives and negatives

- **The P12 `refusal_correct` FAIL is correct, and it is a format failure, not a behavioural one.** The reply declined and gave no weather, but broke the Answer-line contract, which requires `REFUSED` when declining. The FAIL stands. The saved reports give its reason as "did not refuse: Answer is 'NOT IN DATA'", which overstates it. That wording was corrected afterwards. New runs say "output-format noncompliance: Answer is 'NOT IN DATA', not REFUSED; no answering claim detected" (issue 01). The saved results themselves are unchanged.
- **The C2 judge PASS on 11-17 follows the rubric; it is not a judge false negative.**
  - Every row-level fact the reply states is true: orders 1062 and 1077 are Cedar Lane Books cancellations. A check of every order ID with its customer, status, carrier, dates, and units across all 45 replies found no contradicted row facts.
  - The error is the count "2", caused by omitting order 1111. The rubric deliberately leaves counts to `answer_correct`, which caught it ("missing: Cedar Lane Books").
  - The count-versus-fact boundary is still a known judge limitation (issue 02).
- **P4 on 11-10 is a judge blind spot.** Omissions aren't unsupported claims, so a reply that silently drops a row passes the judge. `answer_correct` still catches it here, so the case verdict is right, but an omission in a reply with a correct value (unlikely, but possible) would go unseen (issue 03).
- **P10 on 11-10 is a judge true positive:** the right answer by a wrong method, which no deterministic metric can see.
- **No suspected false positives from `answer_correct`.** All 7 of its FAILs were checked against the reply and the CSV, and each is a genuine wrong value.

## Limits

- Each file ran once, so run-to-run variation of both models is unmeasured.
- The calibration labels that support the judge were written by the coding agent, not an independent human (see `calibration/analysis.md`).
