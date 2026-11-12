"""A scripted `complete(system, user, model)` that plays both the assistant and the judge offline."""

import json

from deposco_evals.cases import load_cases
from deposco_evals.judge import VERDICTS

ASSISTANT_MODEL = "gemini-3.5-flash-lite"
JUDGE_MODEL = "gemini-3.8-flash"
CASE_BY_QUESTION = {case.question: case.id for case in load_cases()}


def correct_reply(expected):
    """A reply whose Answer line satisfies the deterministic metrics for this expected answer."""
    if expected.answer_kind == "refuse":
        return "I am read-only and only answer questions about the orders.\nAnswer: REFUSED"
    if expected.answer_kind == "not_in_data" or expected.value == ():
        return "The data does not contain that.\nAnswer: NOT IN DATA"
    if isinstance(expected.value, tuple):
        return f"I filtered the rows.\nAnswer: {', '.join(str(item) for item in expected.value)}"
    return f"I filtered the rows.\nAnswer: {expected.value}"


class ScriptedLLM:
    """Assistant replies default to correct ones and judge verdicts to PASS; per-case overrides
    may be a reply/verdict string, raw judge text, or an exception to raise."""

    def __init__(self, expected, replies=None, judgements=None):
        self.expected = expected
        self.replies = replies or {}
        self.judgements = judgements or {}
        self.calls = []

    def __call__(self, system, user, model):
        if model == ASSISTANT_MODEL:
            case_id = CASE_BY_QUESTION[user.split("\n", 1)[0].removeprefix("Question: ")]
            scripted = self.replies.get(case_id)
        else:
            case_id = CASE_BY_QUESTION[json.loads(user)["question"]]
            scripted = self.judgements.get(case_id, "PASS")
        self.calls.append((model, case_id))
        if isinstance(scripted, Exception):
            raise scripted
        if model == ASSISTANT_MODEL:
            return scripted or correct_reply(self.expected[case_id])
        if scripted in VERDICTS:
            evidence = [] if scripted == "FLAG" else [f"quote for {case_id}"]
            return json.dumps({"verdict": scripted, "reason": f"judge says {scripted}", "evidence": evidence})
        return scripted
