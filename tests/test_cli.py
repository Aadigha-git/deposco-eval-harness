import json
from pathlib import Path

import pytest
from scripted_llm import ScriptedLLM

from deposco_evals import __main__ as cli
from deposco_evals.ground_truth import RULES, expected_answers
from deposco_evals.llm import LLMError
from deposco_evals.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent

# A fourth file with the same schema, dated on the first of a month; answers worked out by hand.
FOURTH_CSV = """order_id,customer,status,carrier,order_date,ship_date,units
2001,Harbor Goods,open,UPS,2026-11-28,,10
2002,Harbor Goods,open,FedEx,2026-12-01,,5
2003,Juniper Kids,shipped,UPS,2026-11-25,2026-12-01,7
2004,Juniper Kids,cancelled,USPS,2026-12-01,,3
2005,Alder & Finch,shipped,USPS,2026-11-20,2026-11-24,9
"""


@pytest.fixture
def fourth_file(tmp_path):
    path = tmp_path / "orders_2026-12-01.csv"
    path.write_text(FOURTH_CSV.replace("\n", "\r\n"), encoding="utf-8")
    return path


@pytest.fixture
def scripted(monkeypatch):
    """Replaces the Gemini client with the scripted LLM; returns a setter for its per-case overrides."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    overrides = {}

    def fake_make_complete(config):
        snapshot = load_snapshot(overrides["data"])
        return ScriptedLLM(expected_answers(snapshot), overrides.get("replies"), overrides.get("judgements"))

    monkeypatch.setattr(cli, "make_complete", fake_make_complete)
    return overrides


def test_expected_only_prints_ground_truth_without_an_api_key(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    code = cli.main(["--data", str(ROOT / "data" / "orders_2026-11-10.csv"), "--expected-only"])

    assert code == 0
    out = capsys.readouterr().out
    assert "Expected answers for orders_2026-11-10.csv (today 2026-11-10)" in out
    assert "  expected: exactly 450" in out


def test_a_fourth_csv_with_the_same_schema_runs_without_code_changes(fourth_file, scripted, tmp_path, capsys):
    scripted["data"] = fourth_file
    out_dir = tmp_path / "reports"

    code = cli.main(["--data", str(fourth_file), "--out", str(out_dir)])

    assert code == 0
    data = json.loads((out_dir / "orders_2026-12-01.json").read_text(encoding="utf-8"))
    assert data["reference_date"] == "2026-12-01"
    expected = {case["id"]: case["expected"]["value"] for case in data["cases"]}
    assert {key: expected[key] for key in ("P1", "P4", "P6", "P9", "P10", "C1", "C3")} == {
        "P1": 2, "P4": 7, "P6": ["Harbor Goods"], "P9": 22, "P10": ["UPS"], "C1": [2001, 2002], "C3": 1,
    }
    assert data["summary"]["overall"]["PASS"] == 15
    assert (out_dir / "orders_2026-12-01.md").read_text(encoding="utf-8").startswith("# Eval report: orders_2026-12-01.csv")
    assert "PASS 15, FLAG 0, FAIL 0, ERROR 0" in capsys.readouterr().out


def test_a_run_with_failures_still_completes_and_reports_them(scripted, tmp_path, capsys):
    data_file = ROOT / "data" / "orders_2026-11-10.csv"
    scripted.update(data=data_file, replies={"P1": "Counted.\nAnswer: 7"}, judgements={"P6": "FLAG"})

    code = cli.main(["--data", str(data_file), "--out", str(tmp_path)])

    assert code == 0
    assert "PASS 13, FLAG 1, FAIL 1, ERROR 0" in capsys.readouterr().out


def test_a_run_with_some_errors_writes_reports_and_warns(scripted, tmp_path, capsys):
    data_file = ROOT / "data" / "orders_2026-11-10.csv"
    scripted.update(data=data_file, replies={"P4": LLMError("Gemini API returned HTTP 503: unavailable")})

    code = cli.main(["--data", str(data_file), "--out", str(tmp_path)])

    assert code == 0
    assert "warning: 1 case(s) ended in ERROR" in capsys.readouterr().err
    assert json.loads((tmp_path / "orders_2026-11-10.json").read_text(encoding="utf-8"))["summary"]["overall"]["ERROR"] == 1


def test_a_total_outage_exits_2_and_keeps_the_previous_reports(scripted, tmp_path, capsys):
    data_file = ROOT / "data" / "orders_2026-11-10.csv"
    outage = LLMError("Gemini API returned HTTP 401: API key not valid.")
    scripted.update(data=data_file, replies={case_id: outage for case_id in RULES})
    for name in ("orders_2026-11-10.md", "orders_2026-11-10.json"):
        (tmp_path / name).write_text("previous report", encoding="utf-8")

    code = cli.main(["--data", str(data_file), "--out", str(tmp_path)])

    assert code == 2
    err = capsys.readouterr().err
    assert "every case ended in ERROR" in err and "HTTP 401: API key not valid." in err
    assert (tmp_path / "orders_2026-11-10.md").read_text(encoding="utf-8") == "previous report"


def test_an_unwritable_report_directory_exits_2(scripted, tmp_path, capsys):
    data_file = ROOT / "data" / "orders_2026-11-10.csv"
    scripted["data"] = data_file
    not_a_directory = tmp_path / "reports"
    not_a_directory.write_text("", encoding="utf-8")

    code = cli.main(["--data", str(data_file), "--out", str(not_a_directory)])

    assert code == 2
    assert "error: cannot write reports" in capsys.readouterr().err


@pytest.mark.parametrize("failing_suffix", [".md.tmp", ".json.tmp"])
def test_a_failed_report_write_keeps_the_previous_reports_and_leaves_no_temporary_files(
    scripted, tmp_path, monkeypatch, capsys, failing_suffix
):
    data_file = ROOT / "data" / "orders_2026-11-10.csv"
    scripted["data"] = data_file
    for name in ("orders_2026-11-10.md", "orders_2026-11-10.json"):
        (tmp_path / name).write_text("previous report", encoding="utf-8")
    real_write_text = Path.write_text

    def disk_full_for(path, *args, **kwargs):
        if path.name.endswith(failing_suffix):
            raise OSError("No space left on device")
        return real_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", disk_full_for)

    code = cli.main(["--data", str(data_file), "--out", str(tmp_path)])

    assert code == 2
    assert "No space left on device" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["orders_2026-11-10.json", "orders_2026-11-10.md"]
    assert all(p.read_text(encoding="utf-8") == "previous report" for p in tmp_path.iterdir())


def test_a_missing_api_key_stops_before_any_report_is_written(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    code = cli.main(["--data", str(ROOT / "data" / "orders_2026-11-10.csv"), "--out", str(tmp_path)])

    assert code == 2
    assert "GEMINI_API_KEY is not set" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("name", "message"),
    [("orders.csv", "file name must be orders_YYYY-MM-DD.csv"), ("orders_2026-12-02.csv", "No such file")],
)
def test_unusable_data_files_exit_with_code_2_and_one_clear_message(tmp_path, capsys, name, message):
    if name == "orders.csv":
        (tmp_path / name).write_text(FOURTH_CSV, encoding="utf-8")

    code = cli.main(["--data", str(tmp_path / name), "--expected-only"])

    assert code == 2
    assert message in capsys.readouterr().err
