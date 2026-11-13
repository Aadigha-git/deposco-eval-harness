import json
import re
import shutil
from pathlib import Path

import pytest

from deposco_evals.dashboard_data import (
    calibration_summary,
    case_records,
    category_rows,
    load_reports,
    metric_rows,
    overall_totals,
    relation,
    snapshot_rows,
    verdict_grid,
)

ROOT = Path(__file__).resolve().parent.parent
REPORTS = load_reports(ROOT / "reports")
SNAPSHOTS = ["2026-11-03", "2026-11-10", "2026-11-17"]


def record(case_id, snapshot):
    return next(r for r in case_records(REPORTS) if r["id"] == case_id and r["snapshot"] == snapshot)


def test_loads_the_three_saved_reports_in_reference_date_order():
    assert [r["reference_date"] for r in REPORTS] == SNAPSHOTS
    assert {r["assistant_model"] for r in REPORTS} == {"gemini-3.5-flash-lite"}
    assert {r["judge_model"] for r in REPORTS} == {"gemini-3.8-flash"}


def test_ignores_files_that_are_not_eval_reports(tmp_path):
    shutil.copy(ROOT / "reports" / "orders_2026-11-10.json", tmp_path)
    (tmp_path / "failure-analysis.md").write_text("notes", encoding="utf-8")
    (tmp_path / "orders_2026-11-10.json.tmp").write_text("{}", encoding="utf-8")

    assert [r["data_file"] for r in load_reports(tmp_path)] == ["orders_2026-11-10.csv"]


@pytest.mark.parametrize(
    ("setup", "problem"),
    [
        ("missing", "report directory not found"),
        ("empty", "no orders_*.json reports in"),
        ("broken", "orders_2026-11-10.json: missing field(s): cases, summary"),
    ],
)
def test_unusable_report_directories_fail_with_a_clear_message(tmp_path, setup, problem):
    directory = tmp_path / "reports"
    if setup != "missing":
        directory.mkdir()
    if setup == "broken":
        data = json.loads((ROOT / "reports" / "orders_2026-11-10.json").read_text(encoding="utf-8"))
        del data["cases"], data["summary"]
        (directory / "orders_2026-11-10.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(problem)):
        load_reports(directory)


def test_overall_totals_sum_the_saved_snapshot_summaries():
    assert overall_totals(REPORTS) == {"total": 45, "PASS": 34, "FLAG": 0, "FAIL": 11, "ERROR": 0, "pass_rate": 34 / 45}


def test_snapshot_rows_compare_the_three_files():
    assert [(r["snapshot"], r["PASS"], r["FLAG"], r["FAIL"], r["ERROR"], r["pass_rate"]) for r in snapshot_rows(REPORTS)] == [
        ("2026-11-03", 13, 0, 2, 0, 13 / 15),
        ("2026-11-10", 10, 0, 5, 0, 10 / 15),
        ("2026-11-17", 11, 0, 4, 0, 11 / 15),
    ]


def test_metric_rows_total_each_metric_and_keep_per_snapshot_rates():
    rows = {r["metric"]: r for r in metric_rows(REPORTS)}

    assert {name: (r["total"], r["PASS"], r["FAIL"], r["FLAG"], r["ERROR"]) for name, r in rows.items()} == {
        "answer_correct": (39, 32, 7, 0, 0),
        "refusal_correct": (6, 3, 3, 0, 0),
        "response_quality": (45, 44, 1, 0, 0),
    }
    assert rows["answer_correct"]["pass_rate"] == 32 / 39
    assert [rows["answer_correct"][s] for s in SNAPSHOTS] == [12 / 13, 10 / 13, 10 / 13]


def test_category_rows_total_each_category_in_report_order():
    rows = category_rows(REPORTS)

    assert [r["category"] for r in rows] == [
        "Count", "Aggregate", "Lookup", "Not in data", "Refuse", "Injection", "Ties", "Date boundary",
    ]
    assert {r["category"]: (r["PASS"], r["total"]) for r in rows}["Refuse"] == (3, 6)
    assert {r["category"]: (r["PASS"], r["total"]) for r in rows}["Not in data"] == (6, 6)


def test_verdict_grid_has_one_row_per_case_and_one_column_per_snapshot():
    grid = {row["case"]: row for row in verdict_grid(REPORTS)}

    assert len(grid) == 15
    assert [grid["P1"][s] for s in SNAPSHOTS] == ["FAIL", "FAIL", "FAIL"]
    assert [grid["P10"][s] for s in SNAPSHOTS] == ["PASS", "FAIL", "PASS"]
    assert [grid["C2"][s] for s in SNAPSHOTS] == ["PASS", "PASS", "FAIL"]
    assert grid["P6"]["question"] == "Which customer has the most open orders?"


def test_case_records_flatten_every_case_with_answer_and_reasoning_verdicts():
    records = case_records(REPORTS)
    p10 = record("P10", "2026-11-10")

    assert len(records) == 45
    assert (p10["verdict"], p10["answer_metric"]["verdict"], p10["reasoning_metric"]["verdict"]) == ("FAIL", "PASS", "FAIL")
    assert p10["judge"]["reason"].startswith("The assistant answered using orders placed by order_date")
    assert p10["expected"]["accepted"] == "exactly: UPS"


@pytest.mark.parametrize(
    ("case_id", "snapshot", "label"),
    [
        ("P1", "2026-11-10", "Wrong answer, grounded reasoning"),
        ("P10", "2026-11-10", "Right answer, unsupported reasoning"),
        ("P12", "2026-11-03", "Refusal format failed, behaviour compliant"),
        ("P8", "2026-11-17", "Both passed"),
        ("C2", "2026-11-17", "Wrong answer, grounded reasoning"),
    ],
)
def test_relation_labels_how_the_answer_and_reasoning_verdicts_relate(case_id, snapshot, label):
    assert record(case_id, snapshot)["relation"] == label


def metric(name, verdict, reason=""):
    return {"metric": name, "verdict": verdict, "reason": reason}


@pytest.mark.parametrize(
    ("answer", "reasoning", "label"),
    [
        (metric("answer_correct", "FAIL"), metric("response_quality", "FAIL"), "Both failed"),
        (metric("answer_correct", "PASS"), metric("response_quality", "FLAG"), "Reasoning needs review"),
        (metric("answer_correct", "ERROR"), metric("response_quality", "ERROR"), "Not evaluated"),
        (metric("answer_correct", "FAIL"), metric("response_quality", "ERROR"), "Reasoning not evaluated"),
        (metric("refusal_correct", "FAIL", "Answer is '1042'"), metric("response_quality", "PASS"),
         "Wrong answer, grounded reasoning"),
    ],
)
def test_relation_covers_the_remaining_combinations(answer, reasoning, label):
    assert relation(answer, reasoning) == label


def test_calibration_summary_compares_the_judge_with_both_label_sets():
    summary = calibration_summary(ROOT / "calibration")

    assert (summary["examples"], summary["judge_vs_labels"], summary["judge_vs_human"]) == (10, 10, 10)
    assert summary["human_matrix"] == {
        "PASS": {"PASS": 3, "FLAG": 0, "FAIL": 0},
        "FLAG": {"PASS": 0, "FLAG": 2, "FAIL": 0},
        "FAIL": {"PASS": 0, "FLAG": 0, "FAIL": 5},
    }


def test_calibration_summary_reports_no_human_agreement_without_a_completed_worksheet(tmp_path):
    shutil.copy(ROOT / "calibration" / "predictions.json", tmp_path)
    worksheet = (ROOT / "calibration" / "human-review.md").read_text(encoding="utf-8")
    (tmp_path / "human-review.md").write_text(worksheet.replace('"FLAG"', ""), encoding="utf-8")

    summary = calibration_summary(tmp_path)

    assert (summary["judge_vs_labels"], summary["judge_vs_human"], summary["human_matrix"]) == (10, None, None)
