import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="install the dashboard extra to test the app: pip install -e '.[dashboard]'")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "dashboard.py")


def app_with(tmp_path, edit_report=None, calibration=True):
    """A copy of the dashboard reading copied (optionally edited) reports from tmp_path."""
    shutil.copy(APP, tmp_path / "dashboard.py")
    (tmp_path / "reports").mkdir()
    for path in sorted((ROOT / "reports").glob("orders_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if edit_report:
            edit_report(data)
        (tmp_path / "reports" / path.name).write_text(json.dumps(data), encoding="utf-8")
    if calibration:
        shutil.copytree(ROOT / "calibration", tmp_path / "calibration")
    return AppTest.from_file(str(tmp_path / "dashboard.py"), default_timeout=30)


def test_dashboard_renders_the_saved_results_without_errors():
    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert [m.value for m in app.metric][:5] == ["34", "0", "11", "0", "76%"]
    assert [tab.label for tab in app.tabs] == ["Overview", "Answer vs reasoning", "Case explorer", "Judge calibration"]
    assert any("34 of 45 cases passed" in md.value for md in app.markdown)
    assert any("10 of 10" == m.value for m in app.metric)


def test_case_explorer_filters_by_verdict_and_shows_the_chosen_case():
    app = AppTest.from_file(APP, default_timeout=30).run()

    app.multiselect[2].set_value(["FAIL"]).run()

    assert not app.exception
    assert any(c.value == "11 of 45 case results match." for c in app.caption)
    assert app.selectbox[0].options[0] == "P1 on 2026-11-03: FAIL"
    assert any(md.value == "**Question:** How many orders are open?" for md in app.markdown)


def test_missing_calibration_results_leave_the_rest_of_the_page_working(tmp_path):
    app = app_with(tmp_path, calibration=False).run()

    assert not app.exception
    assert [m.value for m in app.metric][:5] == ["34", "0", "11", "0", "76%"]
    assert any("No calibration results found" in info.value for info in app.info)


def test_reports_without_a_spotlight_case_still_render(tmp_path):
    def drop_p10(report):
        report["cases"] = [case for case in report["cases"] if case["id"] != "P10"]

    app = app_with(tmp_path, drop_p10).run()

    assert not app.exception
    assert not any(header.value.startswith("P10:") for header in app.subheader)


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
    assert any("Gemini API timed out after 120s" in warning.value for warning in app.warning)
