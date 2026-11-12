"""Run every golden case against one snapshot: assistant, deterministic metrics, judge, case verdict."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from deposco_evals.assistant import ask
from deposco_evals.cases import Case
from deposco_evals.ground_truth import RULES, ExpectedAnswer, expected_answers
from deposco_evals.judge import JudgeOutputError, JudgeVerdict, judge_reply
from deposco_evals.llm import Complete, LLMError
from deposco_evals.metrics import (
    MetricResult,
    answer_correct,
    refusal_correct,
    response_quality,
    response_quality_error,
    ungraded,
)
from deposco_evals.snapshot import Snapshot

CASE_VERDICTS = ("PASS", "FLAG", "FAIL", "ERROR")


@dataclass(frozen=True)
class CaseResult:
    case: Case
    expected: ExpectedAnswer
    response: str | None
    metrics: tuple[MetricResult, ...]
    judged: JudgeVerdict | None
    verdict: str
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    data_file: str
    reference_date: date
    assistant_model: str
    judge_model: str
    run_at: str
    cases: tuple[CaseResult, ...]


@dataclass(frozen=True)
class Summary:
    overall: dict[str, int]
    by_metric: dict[str, dict[str, int]]
    by_category: dict[str, dict[str, int]]


def run_evals(
    snapshot: Snapshot, cases: list[Case], complete: Complete, assistant_model: str, judge_model: str
) -> RunResult:
    _check_cases_match_rules(cases)
    expected = expected_answers(snapshot)
    results = tuple(
        _run_case(snapshot, case, expected[case.id], complete, assistant_model, judge_model) for case in cases
    )
    return RunResult(
        data_file=snapshot.source_name,
        reference_date=snapshot.today,
        assistant_model=assistant_model,
        judge_model=judge_model,
        run_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        cases=results,
    )


def case_verdict(metrics: tuple[MetricResult, ...]) -> str:
    """FAIL beats ERROR beats FLAG; PASS needs every applicable metric to pass."""
    verdicts = {m.verdict for m in metrics if m.applies}
    for verdict in ("FAIL", "ERROR", "FLAG"):
        if verdict in verdicts:
            return verdict
    return "PASS"


def summarize(run: RunResult) -> Summary:
    by_metric: dict[str, list[str]] = {}
    by_category: dict[str, list[str]] = {}
    for result in run.cases:
        by_category.setdefault(result.case.category, []).append(result.verdict)
        for metric in result.metrics:
            if metric.applies:
                by_metric.setdefault(metric.metric, []).append(metric.verdict)
    return Summary(
        overall=_tally([result.verdict for result in run.cases]),
        by_metric={name: _tally(verdicts) for name, verdicts in by_metric.items()},
        by_category={name: _tally(verdicts) for name, verdicts in by_category.items()},
    )


def pass_rate(tally: dict[str, int]) -> float | None:
    """PASS over everything counted; FLAG and ERROR are never partial passes."""
    return tally["PASS"] / tally["total"] if tally["total"] else None


def _run_case(
    snapshot: Snapshot, case: Case, expected: ExpectedAnswer, complete: Complete, assistant_model: str, judge_model: str
) -> CaseResult:
    try:
        response = ask(snapshot, case.question, complete, assistant_model)
    except Exception as error:  # recorded explicitly so the rest of the run is kept
        problem = f"assistant: {_describe(error)}"
        return CaseResult(case, expected, None, ungraded(expected, problem), None, "ERROR", problem)
    try:
        return _grade(snapshot, case, expected, response, complete, judge_model)
    except Exception as error:  # a grading bug must not lose the other cases
        problem = f"internal: {_describe(error)}"
        return CaseResult(case, expected, response, ungraded(expected, problem), None, "ERROR", problem)


def _grade(
    snapshot: Snapshot, case: Case, expected: ExpectedAnswer, response: str, complete: Complete, judge_model: str
) -> CaseResult:
    judged, error = None, None
    try:
        judged = judge_reply(snapshot, case.question, response, complete, judge_model)
        quality = response_quality(judged)
    except Exception as failure:  # recorded explicitly so the rest of the run is kept
        error = f"judge: {_describe(failure)}"
        quality = response_quality_error(_describe(failure))
    metrics = (answer_correct(expected, response), refusal_correct(expected, response), quality)
    return CaseResult(case, expected, response, metrics, judged, case_verdict(metrics), error)


def _check_cases_match_rules(cases: list[Case]) -> None:
    case_ids = [case.id for case in cases]
    without_rule = [case_id for case_id in case_ids if case_id not in RULES]
    without_case = [case_id for case_id in RULES if case_id not in case_ids]
    if without_rule or without_case:
        raise ValueError(
            "golden cases and ground-truth rules differ: "
            f"cases without a rule: {', '.join(without_rule) or 'none'}; "
            f"rules without a case: {', '.join(without_case) or 'none'}"
        )


def _describe(error: Exception) -> str:
    if isinstance(error, (LLMError, JudgeOutputError)):
        return str(error)
    return f"{type(error).__name__}: {error}"


def _tally(verdicts: list[str]) -> dict[str, int]:
    return {"total": len(verdicts), **{verdict: verdicts.count(verdict) for verdict in CASE_VERDICTS}}
