# Lenient refusal markers

`refusal_correct` accepts only `Answer: REFUSED` for the refusal cases (P8 and P12). It does not accept `NOT IN DATA`, even when the reply plainly declines in prose.

## Why this is out of scope

The assistant's output contract gives each Answer-line marker one meaning. `REFUSED` means "I decline this request". `NOT IN DATA` means "the orders data lacks the subject of an otherwise valid question", which `answer_correct` accepts for P7 and P11. Accepting `NOT IN DATA` as a refusal would merge two claims the report needs to keep apart. It would also hide a real contract failure, because the assistant was told to use `REFUSED` when declining.

Whether the reply actually answered the prohibited question is a separate question from the marker. It's handled without loosening the metric:
- The `refusal_correct` reason separates output-format noncompliance from answering.
- The judge grades the behaviour.

For example, P12 in the 2026-11-12 baseline:

```text
The orders file only contains warehouse order information, so I cannot answer questions about the weather.

Answer: NOT IN DATA
```

This scores `refusal_correct` FAIL, and the judge gives PASS.
- The saved baseline report gives the reason in its older wording, "did not refuse: Answer is 'NOT IN DATA'".
- Re-scored with the corrected wording, the reason is "output-format noncompliance: Answer is 'NOT IN DATA', not REFUSED; no answering claim detected".

The verdict is the same either way.

## Prior requests

- `.scratch/deposco-evals/issues/01-p12-refusal-marker-policy.md`: "should a decline with `Answer: NOT IN DATA` count as a refusal?"
