"""Render one run as a readable Markdown report and as structured JSON, plus --expected-only text."""

import json

from deposco_evals.cases import Case
from deposco_evals.ground_truth import ExpectedAnswer, expected_answers
from deposco_evals.metrics import MetricResult
from deposco_evals.periods import format_window, last_7_days, this_month
from deposco_evals.run import CASE_VERDICTS, CaseResult, RunResult, pass_rate, summarize
from deposco_evals.snapshot import Snapshot


def definitions(run: RunResult) -> dict[str, str]:
    today = run.reference_date
    return {
        "today": "the date in the data file name, never the system clock",
        "last 7 days": f"today and the 6 days before today ({format_window(last_7_days(today))})",
        "this month": f"the calendar month of today ({format_window(this_month(today))})",
        "shipped in a period": "status is shipped and ship_date is in the period",
        "placed in a period": "order_date is in the period",
        "ties": "every item sharing the highest value is the answer",
        "answer_correct": "code; the final Answer line must equal the expected value exactly "
        "(complete tie sets; 0 or NOT IN DATA when the subject is absent); threshold 1",
        "refusal_correct": "code; P8 and P12 must answer REFUSED without claiming a change or giving weather; threshold 1",
        "response_quality": f"LLM judge ({run.judge_model}) with deposco_evals/judge_rubric.md; verdict PASS, FLAG, "
        "or FAIL on grounding and behaviour, not on the number; only PASS passes",
        "Case verdict": "FAIL if any applicable metric fails; otherwise ERROR if the assistant or judge call failed; "
        "otherwise FLAG if the judge flagged the reply for review; otherwise PASS",
        "Pass rate": "PASS divided by the applicable count; FLAG and ERROR never count as passes, "
        "and no scores are averaged",
    }


def render_markdown(run: RunResult) -> str:
    summary = summarize(run)
    lines = [
        f"# Eval report: {run.data_file}",
        "",
        f"- Reference date (today): {run.reference_date.isoformat()}, from the data file name",
        f"- Assistant model: {run.assistant_model}",
        f"- Judge model: {run.judge_model}",
        f"- Run at: {run.run_at}",
        "",
        "## Definitions",
        "",
        *(f"- {term}: {meaning}" for term, meaning in definitions(run).items()),
        "",
        "## Summary",
        "",
        *_tally_table("Scope", {"Overall": summary.overall}),
        "",
        *_tally_table("Metric", summary.by_metric),
        "",
        *_tally_table("Category", summary.by_category),
        "",
        "## Cases",
        "",
    ]
    for result in run.cases:
        lines += _case_section(result)
    return "\n".join(lines) + "\n"


def render_json(run: RunResult) -> str:
    summary = summarize(run)
    data = {
        "data_file": run.data_file,
        "reference_date": run.reference_date.isoformat(),
        "assistant_model": run.assistant_model,
        "judge_model": run.judge_model,
        "run_at": run.run_at,
        "definitions": definitions(run),
        "summary": {
            "overall": _with_rate(summary.overall),
            "by_metric": {name: _with_rate(tally) for name, tally in summary.by_metric.items()},
            "by_category": {name: _with_rate(tally) for name, tally in summary.by_category.items()},
        },
        "cases": [_case_record(result) for result in run.cases],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_expected(snapshot: Snapshot, cases: list[Case]) -> str:
    expected = expected_answers(snapshot)
    lines = [f"Expected answers for {snapshot.source_name} (today {snapshot.today.isoformat()})", ""]
    for case in cases:
        answer = expected[case.id]
        lines += [f"{case.id} {case.question}", f"  expected: {answer.accepted}", f"  rule: {answer.rule}"]
        if answer.order_ids:
            lines.append(f"  orders: {', '.join(map(str, answer.order_ids))}")
        if answer.tallies:
            lines.append(f"  tallies: {_tallies(answer)}")
        lines.append("")
    return "\n".join(lines)


def _tally_table(scope: str, tallies: dict[str, dict[str, int]]) -> list[str]:
    lines = [f"| {scope} | Applicable | " + " | ".join(CASE_VERDICTS) + " | Pass rate |", "|---" * 7 + "|"]
    for name, tally in tallies.items():
        counts = " | ".join(str(tally[verdict]) for verdict in CASE_VERDICTS)
        lines.append(f"| {name} | {tally['total']} | {counts} | {percent(pass_rate(tally))} |")
    return lines


def _case_section(result: CaseResult) -> list[str]:
    expected = result.expected
    lines = [
        f"### {result.case.id} ({result.case.category}): {result.verdict}",
        "",
        f"**Question:** {result.case.question}",
        "",
        f"**Expected answer:** {expected.accepted}",
        "",
        f"**Evidence:** {_evidence(expected)}",
        "",
    ]
    if result.response is None:
        lines += ["**Response:** none, the assistant call failed", ""]
    else:
        quoted = (f"> {_no_html(line)}" if line else ">" for line in result.response.splitlines())
        lines += ["**Response:**", "", *quoted, ""]
    if result.metrics:
        lines += ["| Metric | Verdict | Score | Threshold | Reason |", "|---|---|---|---|---|"]
        lines += [_metric_row(metric) for metric in result.metrics]
        lines.append("")
    if result.judged:
        evidence = "; ".join(_one_line(item) for item in result.judged.evidence) or "(none)"
        lines += [f"**Judge evidence:** {evidence}", ""]
    if result.verdict == "FAIL" and any(m.metric == "response_quality" and m.verdict == "ERROR" for m in result.metrics):
        lines += [
            "**Note:** FAIL comes from the deterministic metrics; response_quality was not evaluated "
            "because the judge errored, so the judge neither passed nor failed this reply.",
            "",
        ]
    if result.error:
        lines += [f"**Error:** {_one_line(result.error)}", ""]
    return lines


def _metric_row(metric: MetricResult) -> str:
    verdict = metric.verdict if metric.applies else "n/a"
    if verdict == "ERROR":
        verdict = "ERROR (not evaluated)"
    score = "-" if metric.score is None else f"{metric.score:g}"
    threshold = "-" if metric.threshold is None else f"{metric.threshold:g}"
    return f"| {metric.metric} | {verdict} | {score} | {threshold} | {_cell(metric.reason)} |"


def _evidence(expected: ExpectedAnswer) -> str:
    parts = [expected.rule]
    if expected.order_ids:
        parts.append(f"orders {', '.join(map(str, expected.order_ids))}")
    if expected.tallies:
        parts.append(f"tallies {_tallies(expected)}")
    return "; ".join(parts)


def _tallies(expected: ExpectedAnswer) -> str:
    ordered = sorted(expected.tallies.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name} {count}" for name, count in ordered)


def _case_record(result: CaseResult) -> dict:
    expected = result.expected
    return {
        "id": result.case.id,
        "category": result.case.category,
        "question": result.case.question,
        "expected": {
            "answer_kind": expected.answer_kind,
            "value": list(expected.value) if isinstance(expected.value, tuple) else expected.value,
            "accepted": expected.accepted,
            "rule": expected.rule,
            "order_ids": list(expected.order_ids),
            "tallies": expected.tallies,
        },
        "response": result.response,
        "metrics": [
            {
                "metric": m.metric,
                "applies": m.applies,
                "evaluated": m.applies and m.verdict != "ERROR",
                "verdict": m.verdict,
                "score": m.score,
                "threshold": m.threshold,
                "passed": m.passed,
                "reason": m.reason,
            }
            for m in result.metrics
        ],
        "judge": (
            {"verdict": result.judged.verdict, "reason": result.judged.reason, "evidence": list(result.judged.evidence)}
            if result.judged
            else None
        ),
        "verdict": result.verdict,
        "error": result.error,
    }


def _with_rate(tally: dict[str, int]) -> dict:
    return {**tally, "pass_rate": pass_rate(tally)}


def percent(rate: float | None) -> str:
    return "n/a" if rate is None else f"{round(100 * rate)}%"


def _one_line(text: str) -> str:
    """Model text is shown on one line, without HTML, so it cannot add headings, lists, or markup."""
    return _no_html(" ".join(text.split()))


def _no_html(text: str) -> str:
    return text.replace("<", "&lt;")


def _cell(text: str) -> str:
    return _one_line(text).replace("|", "\\|")
