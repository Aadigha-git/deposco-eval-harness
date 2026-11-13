"""One live assistant question for the dashboard playground, graded with the existing deterministic metrics.

Nothing here is saved: the result lives only in the caller's session.
"""

from dataclasses import dataclass

from deposco_evals.assistant import ask
from deposco_evals.cases import Case
from deposco_evals.extract import normalize_name, parse_answer
from deposco_evals.ground_truth import ExpectedAnswer, expected_answers
from deposco_evals.llm import Complete
from deposco_evals.metrics import MetricResult, answer_correct, refusal_correct
from deposco_evals.snapshot import Snapshot


@dataclass(frozen=True)
class LiveResult:
    question: str
    reply: str
    answer: str | None
    case: Case | None
    expected: ExpectedAnswer | None
    metrics: tuple[MetricResult, ...]


def matching_case(question: str, cases: list[Case]) -> Case | None:
    """The golden case whose question this is, ignoring case and spacing; None for any other question."""
    wanted = normalize_name(question)
    return next((case for case in cases if wanted and normalize_name(case.question) == wanted), None)


def ask_live(snapshot: Snapshot, question: str, cases: list[Case], complete: Complete, model: str) -> LiveResult:
    reply = ask(snapshot, question, complete, model)
    case = matching_case(question, cases)
    if case is None:
        return LiveResult(question, reply, parse_answer(reply), None, None, ())
    expected = expected_answers(snapshot)[case.id]
    graded = (answer_correct(expected, reply), refusal_correct(expected, reply))
    return LiveResult(question, reply, parse_answer(reply), case, expected, tuple(m for m in graded if m.applies))
