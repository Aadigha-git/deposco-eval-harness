import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="install the dashboard extra to test the app: pip install -e '.[dashboard]'")
from scripted_llm import ScriptedLLM  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from deposco_evals import llm  # noqa: E402
from deposco_evals.ground_truth import expected_answers  # noqa: E402
from deposco_evals.snapshot import load_snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "dashboard.py")
PLAYGROUND = "dashboard_pages/playground.py"


def app_with(tmp_path, edit_report=None, calibration=True):
    """A copy of the dashboard reading copied (optionally edited) reports from tmp_path."""
    shutil.copy(APP, tmp_path / "dashboard.py")
    shutil.copytree(ROOT / "dashboard_pages", tmp_path / "dashboard_pages")
    shutil.copytree(ROOT / "data", tmp_path / "data")
    (tmp_path / "reports").mkdir()
    for path in sorted((ROOT / "reports").glob("orders_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if edit_report:
            edit_report(data)
        (tmp_path / "reports" / path.name).write_text(json.dumps(data), encoding="utf-8")
    if calibration:
        shutil.copytree(ROOT / "calibration", tmp_path / "calibration")
    return AppTest.from_file(str(tmp_path / "dashboard.py"), default_timeout=30)


def text(app, kind="markdown"):
    return " ".join(element.value for element in getattr(app, kind))


def test_evaluation_dashboard_shows_the_saved_headline_snapshots_and_sections():
    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert "34 of 45 cases passed" in text(app)
    assert "<b>76%</b>pass rate" in text(app)
    assert all(f"**{day}**" in text(app) for day in ("2026-11-03", "2026-11-10", "2026-11-17"))
    assert [tab.label for tab in app.tabs] == [
        "Case grid", "Metrics and categories", "Answer vs reasoning", "Case explorer", "Judge calibration",
    ]
    assert any(m.value == "10 of 10" for m in app.metric)


def test_case_explorer_filters_by_verdict_and_shows_the_chosen_case():
    app = AppTest.from_file(APP, default_timeout=30).run()

    app.multiselect[2].set_value(["FAIL"]).run()

    assert not app.exception
    assert "11 of 45 case results match." in text(app, "caption")
    assert app.selectbox[0].options[0] == "P1 on 2026-11-03: FAIL"
    assert "**Question:** How many orders are open?" in text(app)


def test_missing_calibration_results_leave_the_rest_of_the_page_working(tmp_path):
    app = app_with(tmp_path, calibration=False).run()

    assert not app.exception
    assert "34 of 45 cases passed" in text(app)
    assert "No calibration results found" in text(app, "info")


def test_reports_without_a_spotlight_case_still_render(tmp_path):
    def drop_p10(report):
        report["cases"] = [case for case in report["cases"] if case["id"] != "P10"]

    app = app_with(tmp_path, drop_p10).run()

    assert not app.exception
    assert "#### P10:" not in text(app)


def test_an_errored_case_can_be_inspected(tmp_path):
    def assistant_failed_on_p3(report):
        case = next(c for c in report["cases"] if c["id"] == "P3")
        case.update(verdict="ERROR", response=None, judge=None, error="assistant: Gemini API timed out after 120s")
        for metric in case["metrics"]:
            if metric["applies"]:
                metric.update(verdict="ERROR", score=None, passed=None, evaluated=False, reason="not graded")

    app = app_with(tmp_path, assistant_failed_on_p3).run()
    app.multiselect[2].set_value(["ERROR"]).run()

    assert not app.exception
    assert app.selectbox[0].options[0] == "P3 on 2026-11-03: ERROR"
    assert "Gemini API timed out after 120s" in text(app, "warning")


def test_a_malformed_calibration_file_is_reported_rather_than_called_missing(tmp_path):
    app = app_with(tmp_path)
    (tmp_path / "calibration" / "predictions.json").write_text("{", encoding="utf-8")
    app.run()

    assert not app.exception
    assert "Could not read the calibration results" in text(app, "error")
    assert "No calibration results found" not in text(app, "info")


def playground(monkeypatch, api_key=True, complete=None, app=None):
    if api_key:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    else:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    if complete is not None:
        monkeypatch.setattr(llm, "make_complete", lambda config: complete)
    app = (AppTest.from_file(APP, default_timeout=30) if app is None else app).run()
    return app.switch_page(PLAYGROUND).run()


def test_playground_without_an_api_key_explains_what_to_do_and_disables_the_run(monkeypatch):
    app = playground(monkeypatch, api_key=False)

    assert not app.exception
    assert "Live runs need a Gemini API key" in text(app, "info")
    assert app.button[0].disabled
    assert "Choose a snapshot and a question" in text(app)


def test_playground_runs_a_golden_case_live_and_keeps_it_apart_from_the_saved_baseline(monkeypatch):
    snapshot = load_snapshot(ROOT / "data" / "orders_2026-11-17.csv")
    scripted = ScriptedLLM(expected_answers(snapshot), replies={"P1": "I counted the open rows.\nAnswer: 14"})
    app = playground(monkeypatch, complete=scripted)

    app.button[0].click().run()

    page = text(app)
    assert not app.exception
    assert "Live run on orders_2026-11-17.csv, not saved" in page
    assert '<div class="answer-value">14</div>' in page
    assert "Expected answer: exactly 15" in page
    assert "`answer_correct`: expected 15, got 14" in page
    assert "Saved baseline report" in page
    assert "the judge is not called in the playground" in text(app, "caption")


def test_playground_answers_a_custom_question_without_grading_it(monkeypatch):
    app = playground(monkeypatch, complete=lambda system, user, model: "Two orders.\nAnswer: 2")

    app.radio[0].set_value("Your own question").run()
    app.text_area[0].input("How many orders did Harbor Goods place?").run()
    app.button[0].click().run()

    assert not app.exception
    assert '<div class="answer-value">2</div>' in text(app)
    assert "Not a golden case" in text(app, "caption")
    assert "Saved baseline report" not in text(app)


def test_playground_shows_an_api_failure_as_a_clear_error(monkeypatch):
    def failing(system, user, model):
        raise llm.LLMError("Gemini API returned HTTP 401: API key not valid.")

    app = playground(monkeypatch, complete=failing)
    app.button[0].click().run()

    assert not app.exception
    assert "The live run failed: Gemini API returned HTTP 401: API key not valid." in text(app, "error")


def test_playground_escapes_model_text_quoted_in_a_metric_reason(monkeypatch):
    snapshot = load_snapshot(ROOT / "data" / "orders_2026-11-17.csv")
    app = playground(monkeypatch, complete=ScriptedLLM(expected_answers(snapshot), replies={"P1": "Answer: <value>"}))

    app.button[0].click().run()

    assert "&lt;value&gt;&#x27; is not a whole number" in text(app)
    assert "<value>" not in text(app)


def test_playground_compares_the_live_answer_check_with_the_saved_answer_check(monkeypatch):
    snapshot = load_snapshot(ROOT / "data" / "orders_2026-11-10.csv")
    app = playground(monkeypatch, complete=ScriptedLLM(expected_answers(snapshot)))
    app.selectbox[0].select("orders_2026-11-10.csv").run()
    app.selectbox[1].select(next(c for c in app.selectbox[1].options if c.startswith("P10:"))).run()

    app.button[0].click().run()

    page = text(app)
    assert not app.exception
    assert '<span class="pill pill-PASS">PASS</span> `answer_correct`' in page
    assert ('saved answer verdict <span class="pill pill-PASS">PASS</span> and final verdict '
            '<span class="pill pill-FAIL">FAIL</span>') in page


def test_playground_marks_a_live_result_as_stale_once_the_question_changes(monkeypatch):
    snapshot = load_snapshot(ROOT / "data" / "orders_2026-11-17.csv")
    app = playground(monkeypatch, complete=ScriptedLLM(expected_answers(snapshot)))
    app.button[0].click().run()

    app.selectbox[1].select(next(c for c in app.selectbox[1].options if c.startswith("P2:"))).run()

    assert "This result is for an earlier question or snapshot" in text(app, "warning")


def test_playground_shows_an_unreadable_snapshot_as_a_clear_error(monkeypatch, tmp_path):
    app = app_with(tmp_path)
    (tmp_path / "data" / "orders_2026-12-01.csv").write_bytes("order_id,customer\n1,Café\n".encode("latin-1"))
    app = playground(monkeypatch, complete=lambda system, user, model: "Answer: 1", app=app)

    app.button[0].click().run()

    assert not app.exception
    assert "The live run failed" in text(app, "error")
