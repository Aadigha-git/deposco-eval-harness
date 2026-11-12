from pathlib import Path

import pytest
from scripted_llm import ASSISTANT_MODEL, JUDGE_MODEL, ScriptedLLM

from deposco_evals import run as run_module
from deposco_evals.cases import Case, load_cases
from deposco_evals.ground_truth import expected_answers
from deposco_evals.llm import LLMError
from deposco_evals.run import pass_rate, run_evals, summarize
from deposco_evals.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = load_snapshot(ROOT / "data" / "orders_2026-11-10.csv")
EXPECTED = expected_answers(SNAPSHOT)
CASES = load_cases()


def run(replies=None, judgements=None, cases=CASES, snapshot=SNAPSHOT):
    llm = ScriptedLLM(expected_answers(snapshot), replies, judgements)
    return run_evals(snapshot, cases, llm, ASSISTANT_MODEL, JUDGE_MODEL), llm


def case(result, case_id):
    return next(c for c in result.cases if c.case.id == case_id)


def test_a_fully_correct_run_passes_every_case_and_records_everything_per_case():
    result, llm = run()

    assert [c.verdict for c in result.cases] == ["PASS"] * 15
    assert llm.calls == [call for c in CASES for call in ((ASSISTANT_MODEL, c.id), (JUDGE_MODEL, c.id))]
    assert (result.data_file, result.reference_date.isoformat()) == ("orders_2026-11-10.csv", "2026-11-10")
    assert (result.assistant_model, result.judge_model) == (ASSISTANT_MODEL, JUDGE_MODEL)
    p1 = case(result, "P1")
    assert (p1.case.question, p1.expected.value, p1.response) == ("How many orders are open?", 8, "I filtered the rows.\nAnswer: 8")
    assert [(m.metric, m.applies, m.verdict) for m in p1.metrics] == [
        ("answer_correct", True, "PASS"), ("refusal_correct", False, None), ("response_quality", True, "PASS"),
    ]
    assert (p1.judged.reason, p1.judged.evidence, p1.error) == ("judge says PASS", ("quote for P1",), None)


@pytest.mark.parametrize(
    ("case_id", "reply", "judgement", "verdict"),
    [
        ("P1", None, "PASS", "PASS"),
        ("P1", None, "FLAG", "FLAG"),
        ("P1", None, "FAIL", "FAIL"),
        ("P1", "Counted.\nAnswer: 7", "PASS", "FAIL"),
        ("P1", "Counted.\nAnswer: 7", "FLAG", "FAIL"),
        ("P1", "Counted.\nAnswer: 7", "FAIL", "FAIL"),
        ("P1", "Counted.\nAnswer: 7", "not json", "FAIL"),
        ("P1", "Counted.\nAnswer: 7", LLMError("Gemini API timed out after 120s"), "FAIL"),
        ("P1", None, "not json", "ERROR"),
        ("P1", None, LLMError("Gemini API returned HTTP 503: unavailable"), "ERROR"),
        ("P8", None, "PASS", "PASS"),
        ("P8", None, "FLAG", "FLAG"),
        ("P8", "Done, cancelled.\nAnswer: 1042", "PASS", "FAIL"),
        ("P8", "Done, cancelled.\nAnswer: 1042", "FLAG", "FAIL"),
        ("P8", "Done, cancelled.\nAnswer: 1042", "not json", "FAIL"),
        ("P8", None, LLMError("Gemini API timed out after 120s"), "ERROR"),
    ],
    ids=[
        "pass+pass", "pass+flag", "pass+judge-fail", "fail+pass", "fail+flag", "fail+judge-fail",
        "fail+malformed-judge", "fail+judge-api-error", "pass+malformed-judge", "pass+judge-api-error",
        "refusal-pass+pass", "refusal-pass+flag", "refusal-fail+pass", "refusal-fail+flag",
        "refusal-fail+malformed-judge", "refusal-pass+judge-api-error",
    ],
)
def test_case_verdict_combinations(case_id, reply, judgement, verdict):
    result, _ = run({case_id: reply} if reply else None, {case_id: judgement})

    assert case(result, case_id).verdict == verdict


def test_a_judge_error_is_explicit_and_never_counted_as_a_pass():
    result, _ = run(judgements={"P1": "not json"})

    p1 = case(result, "P1")
    quality = p1.metrics[-1]
    assert (quality.metric, quality.verdict, quality.passed) == ("response_quality", "ERROR", None)
    assert p1.judged is None
    assert p1.error.startswith("judge: judge output is not a single JSON object")


def test_assistant_failures_are_explicit_and_keep_every_other_case():
    result, llm = run(replies={
        "P3": LLMError("Gemini API returned HTTP 429: quota exceeded"),
        "P5": RuntimeError("connection pool exploded"),
    })

    p3, p5 = case(result, "P3"), case(result, "P5")
    assert (p3.verdict, p3.response, p3.error) == ("ERROR", None, "assistant: Gemini API returned HTTP 429: quota exceeded")
    assert [(m.metric, m.applies, m.verdict, m.passed) for m in p3.metrics] == [
        ("answer_correct", True, "ERROR", None),
        ("refusal_correct", False, None, None),
        ("response_quality", True, "ERROR", None),
    ]
    assert (p5.verdict, p5.error) == ("ERROR", "assistant: RuntimeError: connection pool exploded")
    assert (JUDGE_MODEL, "P3") not in llm.calls
    assert [c.verdict for c in result.cases if c.case.id not in ("P3", "P5")] == ["PASS"] * 13


def test_ungraded_cases_stay_in_every_applicable_metric_denominator():
    result, _ = run(replies={"P1": LLMError("Gemini API timed out after 120s"), "P8": LLMError("boom")})

    by_metric = summarize(result).by_metric

    assert by_metric["answer_correct"] == {"total": 13, "PASS": 12, "FLAG": 0, "FAIL": 0, "ERROR": 1}
    assert by_metric["refusal_correct"] == {"total": 2, "PASS": 1, "FLAG": 0, "FAIL": 0, "ERROR": 1}
    assert by_metric["response_quality"] == {"total": 15, "PASS": 13, "FLAG": 0, "FAIL": 0, "ERROR": 2}


def test_an_internal_bug_while_grading_one_case_keeps_the_rest_of_the_run(monkeypatch):
    real = run_module.answer_correct

    def broken_for_p2(expected, response):
        if expected.case_id == "P2":
            raise ZeroDivisionError("division by zero")
        return real(expected, response)

    monkeypatch.setattr(run_module, "answer_correct", broken_for_p2)

    result, _ = run()

    p2 = case(result, "P2")
    assert (p2.verdict, p2.error) == ("ERROR", "internal: ZeroDivisionError: division by zero")
    assert p2.response == "I filtered the rows.\nAnswer: 6"
    assert sum(c.verdict == "PASS" for c in result.cases) == 14


def test_cases_that_do_not_match_the_ground_truth_rules_are_rejected_before_any_llm_call():
    llm = ScriptedLLM(EXPECTED)

    with pytest.raises(ValueError, match="cases without a rule: P99; rules without a case: C3"):
        run_evals(SNAPSHOT, [*CASES[:-1], Case("P99", "Count", "How many?")], llm, ASSISTANT_MODEL, JUDGE_MODEL)

    assert llm.calls == []


def test_aggregation_counts_each_verdict_separately_by_metric_category_and_overall():
    result, _ = run(
        replies={"P2": "Counted.\nAnswer: 99"},
        judgements={"P1": "FLAG", "P8": LLMError("Gemini API timed out after 120s")},
    )

    summary = summarize(result)

    assert summary.overall == {"total": 15, "PASS": 12, "FLAG": 1, "FAIL": 1, "ERROR": 1}
    assert pass_rate(summary.overall) == 12 / 15
    assert summary.by_metric["answer_correct"] == {"total": 13, "PASS": 12, "FLAG": 0, "FAIL": 1, "ERROR": 0}
    assert summary.by_metric["refusal_correct"] == {"total": 2, "PASS": 2, "FLAG": 0, "FAIL": 0, "ERROR": 0}
    assert summary.by_metric["response_quality"] == {"total": 15, "PASS": 13, "FLAG": 1, "FAIL": 0, "ERROR": 1}
    assert summary.by_category["Count"] == {"total": 3, "PASS": 1, "FLAG": 1, "FAIL": 1, "ERROR": 0}
    assert summary.by_category["Refuse"] == {"total": 2, "PASS": 1, "FLAG": 0, "FAIL": 0, "ERROR": 1}
    assert list(summary.by_category) == [
        "Count", "Aggregate", "Lookup", "Not in data", "Refuse", "Injection", "Ties", "Date boundary",
    ]


def test_pass_rate_is_undefined_without_applicable_results():
    assert pass_rate({"total": 0, "PASS": 0, "FLAG": 0, "FAIL": 0, "ERROR": 0}) is None
