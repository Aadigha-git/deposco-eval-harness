from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="install the dashboard extra to test the app: pip install -e '.[dashboard]'")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "dashboard.py")


def test_dashboard_renders_the_saved_results_without_errors():
    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert [m.value for m in app.metric][:5] == ["34", "0", "11", "0", "76%"]
    assert [tab.label for tab in app.tabs] == ["Overview", "Answer vs reasoning", "Case explorer", "Judge calibration"]
    assert any("34 of 45 graded cases passed" in md.value for md in app.markdown)
    assert any("10 of 10" == m.value for m in app.metric)


def test_case_explorer_filters_by_verdict_and_shows_the_chosen_case():
    app = AppTest.from_file(APP, default_timeout=30).run()

    app.multiselect[2].set_value(["FAIL"]).run()

    assert not app.exception
    assert any(c.value == "11 of 45 case results match." for c in app.caption)
    assert app.selectbox[0].options[0] == "P1 on 2026-11-03: FAIL"
    assert any(md.value == "**Question:** How many orders are open?" for md in app.markdown)
