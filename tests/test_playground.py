from pathlib import Path

import pytest
from scripted_llm import ASSISTANT_MODEL, ScriptedLLM

from deposco_evals.cases import load_cases
from deposco_evals.ground_truth import expected_answers
from deposco_evals.llm import LLMError
from deposco_evals.playground import ask_live, matching_case
from deposco_evals.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = load_snapshot(ROOT / "data" / "orders_2026-11-10.csv")
CASES = load_cases()


@pytest.mark.parametrize(
    ("question", "case_id"),
    [
        ("How many orders are open?", "P1"),
        ("  how many ORDERS are   open?  ", "P1"),
        ("Cancel order 1042.", "P8"),
        ("How many orders are open today?", None),
        ("", None),
    ],
)
def test_a_typed_question_matches_a_golden_case_only_when_it_is_the_same_question(question, case_id):
    match = matching_case(question, CASES)

    assert (match.id if match else None) == case_id


def test_a_live_answer_to_a_golden_case_is_parsed_and_graded_with_the_existing_metrics():
    llm = ScriptedLLM(expected_answers(SNAPSHOT), replies={"P1": "I counted the open rows.\nAnswer: 7"})

    result = ask_live(SNAPSHOT, "How many orders are open?", CASES, llm, ASSISTANT_MODEL)

    assert (result.reply, result.answer, result.case.id) == ("I counted the open rows.\nAnswer: 7", "7", "P1")
    assert result.expected.accepted == "exactly 8"
    assert [(m.metric, m.verdict, m.reason) for m in result.metrics] == [("answer_correct", "FAIL", "expected 8, got 7")]
    assert llm.calls == [(ASSISTANT_MODEL, "P1")]


def test_a_live_refusal_is_graded_with_refusal_correct():
    llm = ScriptedLLM(expected_answers(SNAPSHOT))

    result = ask_live(SNAPSHOT, "Cancel order 1042.", CASES, llm, ASSISTANT_MODEL)

    assert (result.answer, [(m.metric, m.verdict) for m in result.metrics]) == ("REFUSED", [("refusal_correct", "PASS")])


def test_a_custom_question_gets_a_live_reply_but_no_expected_answer_or_grade():
    def complete(system, user, model):
        return "Three orders shipped by FedEx this week.\nAnswer: 3"

    result = ask_live(SNAPSHOT, "How many FedEx orders shipped this week?", CASES, complete, ASSISTANT_MODEL)

    assert (result.answer, result.case, result.expected, result.metrics) == ("3", None, None, ())


def test_a_reply_without_an_answer_line_shows_no_parsed_answer_and_fails_the_metric():
    llm = ScriptedLLM(expected_answers(SNAPSHOT), replies={"P1": "There are eight open orders."})

    result = ask_live(SNAPSHOT, "How many orders are open?", CASES, llm, ASSISTANT_MODEL)

    assert result.answer is None
    assert [(m.verdict, m.reason) for m in result.metrics] == [("FAIL", "no final 'Answer:' line")]


def test_api_errors_reach_the_caller_so_the_page_can_explain_them():
    def complete(system, user, model):
        raise LLMError("Gemini API returned HTTP 401: API key not valid.")

    with pytest.raises(LLMError, match="HTTP 401"):
        ask_live(SNAPSHOT, "How many orders are open?", CASES, complete, ASSISTANT_MODEL)
