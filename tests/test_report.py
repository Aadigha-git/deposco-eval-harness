import json
from pathlib import Path

from scripted_llm import ASSISTANT_MODEL, JUDGE_MODEL, ScriptedLLM

from deposco_evals.cases import load_cases
from deposco_evals.ground_truth import expected_answers
from deposco_evals.llm import LLMError
from deposco_evals.report import render_expected, render_json, render_markdown
from deposco_evals.run import run_evals
from deposco_evals.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = load_snapshot(ROOT / "data" / "orders_2026-11-10.csv")
LLM = ScriptedLLM(
    expected_answers(SNAPSHOT),
    replies={
        "P1": "Counting rows with status open gives 7.\nAnswer: 7",
        "P3": LLMError("Gemini API returned HTTP 503: unavailable"),
    },
    judgements={"P6": "FLAG", "P9": "FAIL", "P10": "not json"},
)
RUN = run_evals(SNAPSHOT, load_cases(), LLM, ASSISTANT_MODEL, JUDGE_MODEL)


def test_markdown_report_states_run_context_and_evaluation_definitions():
    report = render_markdown(RUN)

    for expected in (
        "# Eval report: orders_2026-11-10.csv",
        "- Reference date (today): 2026-11-10, from the data file name",
        f"- Assistant model: {ASSISTANT_MODEL}",
        f"- Judge model: {JUDGE_MODEL}",
        f"- Run at: {RUN.run_at}",
        "- last 7 days: today and the 6 days before today (2026-11-04 to 2026-11-10)",
        "- this month: the calendar month of today (2026-11-01 to 2026-11-30)",
        "- Case verdict: FAIL if any applicable metric fails; otherwise ERROR",
        "FLAG and ERROR never count as passes",
    ):
        assert expected in report, expected


def test_markdown_report_summarises_by_metric_category_and_overall_with_flag_kept_separate():
    report = render_markdown(RUN)

    for expected in (
        "| Overall | 15 | 10 | 1 | 2 | 2 | 67% |",
        "| answer_correct | 13 | 11 | 0 | 1 | 1 | 85% |",
        "| refusal_correct | 2 | 2 | 0 | 0 | 0 | 100% |",
        "| response_quality | 15 | 11 | 1 | 1 | 2 | 73% |",
        "| Count | 3 | 1 | 0 | 1 | 1 | 33% |",
        "| Lookup | 2 | 0 | 1 | 0 | 1 | 0% |",
    ):
        assert expected in report, expected


def test_markdown_report_shows_every_required_per_case_field():
    report = render_markdown(RUN)

    for expected in (
        "### P1 (Count): FAIL",
        "**Question:** How many orders are open?",
        "**Expected answer:** exactly 8",
        "**Evidence:** count of orders where status is open; orders 1082, 1091, 1093, 1095, 1099, 1101, 1102, 1103",
        "> Counting rows with status open gives 7.",
        "| answer_correct | FAIL | 0 | 1 | expected 8, got 7 |",
        "| refusal_correct | n/a | - | - | not a refusal case |",
        "| response_quality | PASS | 1 | 1 | PASS: judge says PASS |",
        "**Judge evidence:** quote for P1",
        "### P3 (Count): ERROR",
        "**Error:** assistant: Gemini API returned HTTP 503: unavailable",
        "### P6 (Lookup): FLAG",
        "tallies Alder & Finch 2,",
        "### P10 (Lookup): ERROR",
        "| response_quality | ERROR (not evaluated) | - | 1 | judge error: judge output is not a single JSON object: 'not json' |",
    ):
        assert expected in report, expected


def test_json_report_carries_the_same_run_as_structured_data():
    data = json.loads(render_json(RUN))

    assert (data["data_file"], data["reference_date"]) == ("orders_2026-11-10.csv", "2026-11-10")
    assert (data["assistant_model"], data["judge_model"]) == (ASSISTANT_MODEL, JUDGE_MODEL)
    assert "last 7 days" in data["definitions"]
    assert data["summary"]["overall"] == {"total": 15, "PASS": 10, "FLAG": 1, "FAIL": 2, "ERROR": 2, "pass_rate": 10 / 15}
    assert data["summary"]["by_category"]["Lookup"]["FLAG"] == 1
    p1 = data["cases"][0]
    assert {key: p1[key] for key in ("id", "category", "question", "verdict", "error")} == {
        "id": "P1", "category": "Count", "question": "How many orders are open?", "verdict": "FAIL", "error": None,
    }
    assert p1["expected"]["value"] == 8 and p1["expected"]["order_ids"][0] == 1082
    assert p1["response"] == "Counting rows with status open gives 7.\nAnswer: 7"
    assert p1["metrics"][0] == {
        "metric": "answer_correct", "applies": True, "evaluated": True, "verdict": "FAIL", "score": 0.0, "threshold": 1.0,
        "passed": False, "reason": "expected 8, got 7",
    }
    assert p1["judge"] == {"verdict": "PASS", "reason": "judge says PASS", "evidence": ["quote for P1"]}
    p3 = data["cases"][2]
    assert (p3["verdict"], p3["response"], p3["judge"]) == ("ERROR", None, None)
    assert [m["verdict"] for m in p3["metrics"]] == ["ERROR", None, "ERROR"]


def test_a_deterministic_fail_with_a_judge_error_stays_fail_and_marks_the_judge_not_evaluated():
    llm = ScriptedLLM(
        expected_answers(SNAPSHOT),
        replies={"P1": "Counting rows with status open gives 7.\nAnswer: 7"},
        judgements={"P1": LLMError("Gemini API returned HTTP 503: unavailable")},
    )
    run = run_evals(SNAPSHOT, load_cases(), llm, ASSISTANT_MODEL, JUDGE_MODEL)

    report = render_markdown(run)
    p1 = json.loads(render_json(run))["cases"][0]

    assert "### P1 (Count): FAIL" in report
    assert "| answer_correct | FAIL | 0 | 1 | expected 8, got 7 |" in report
    assert ("| response_quality | ERROR (not evaluated) | - | 1 | "
            "judge error: Gemini API returned HTTP 503: unavailable |") in report
    assert ("**Note:** FAIL comes from the deterministic metrics; response_quality was not evaluated "
            "because the judge errored, so the judge neither passed nor failed this reply.") in report
    quality = p1["metrics"][2]
    assert (p1["verdict"], p1["judge"]) == ("FAIL", None)
    assert (quality["verdict"], quality["evaluated"], quality["passed"], quality["score"]) == ("ERROR", False, None, None)
    assert [m["evaluated"] for m in p1["metrics"]] == [True, False, False]


def test_a_judged_case_has_no_not_evaluated_note():
    assert "**Note:**" not in render_markdown(RUN).split("### P1 (Count)")[1].split("### P2")[0]


def test_model_text_cannot_add_markdown_structure_to_the_report():
    llm = ScriptedLLM(expected_answers(SNAPSHOT), judgements={
        "P1": '{"verdict": "FAIL", "reason": "bad\\n## Injected", "evidence": ["x\\n# Injected"]}',
    })

    report = render_markdown(run_evals(SNAPSHOT, load_cases(), llm, ASSISTANT_MODEL, JUDGE_MODEL))

    assert not any(line.startswith(("# Injected", "## Injected")) for line in report.splitlines())


def test_model_text_cannot_inject_html_into_the_report():
    llm = ScriptedLLM(
        expected_answers(SNAPSHOT),
        replies={"P1": "<img src=x onerror=alert(1)> 8 open.\nAnswer: 8"},
        judgements={"P1": '{"verdict": "FAIL", "reason": "<b>bold</b>", "evidence": ["<script>x</script>"]}'},
    )

    report = render_markdown(run_evals(SNAPSHOT, load_cases(), llm, ASSISTANT_MODEL, JUDGE_MODEL))

    assert "<img" not in report and "<b>" not in report and "<script>" not in report
    assert "> &lt;img src=x onerror=alert(1)> 8 open." in report
    assert "**Judge evidence:** &lt;script>x&lt;/script>" in report


def test_expected_only_lists_every_case_with_its_expected_answer_and_evidence():
    text = render_expected(SNAPSHOT, load_cases())

    assert "Expected answers for orders_2026-11-10.csv (today 2026-11-10)" in text
    assert "P6 Which customer has the most open orders?" in text
    assert "expected: exactly: Alder & Finch, Elm Street Coffee, Juniper Kids" in text
    assert "P8 Cancel order 1042." in text
    assert "order 1042 is in this file (status shipped)" in text
    assert text.count("expected: ") == 15
