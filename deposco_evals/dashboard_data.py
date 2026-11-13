"""Read-only views over the saved eval reports and calibration results, for the dashboard.

Every number comes from the saved files: summaries are summed, verdicts are copied, nothing is re-graded.
"""

import json
import re
from pathlib import Path

REQUIRED_FIELDS = ("data_file", "reference_date", "assistant_model", "judge_model", "run_at", "summary", "cases")
VERDICTS = ("PASS", "FLAG", "FAIL", "ERROR")
JUDGE_VERDICTS = ("PASS", "FLAG", "FAIL")
DETERMINISTIC_METRICS = ("answer_correct", "refusal_correct")
HUMAN_VERDICT = re.compile(r"^## Example \d+ of 10: (cal-\d+)$.*?^- Verdict \(PASS / FLAG / FAIL\):([^\n]*)$", re.M | re.S)


def load_reports(directory: str | Path) -> list[dict]:
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"report directory not found: {directory}")
    reports = []
    for path in sorted(directory.glob("orders_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = sorted(field for field in REQUIRED_FIELDS if field not in data)
        if missing:
            raise ValueError(f"{path.name}: missing field(s): {', '.join(missing)}")
        reports.append(data)
    if not reports:
        raise ValueError(f"no orders_*.json reports in {directory}")
    return sorted(reports, key=lambda report: report["reference_date"])


def overall_totals(reports: list[dict]) -> dict:
    return _with_rate(_sum(report["summary"]["overall"] for report in reports))


def snapshot_rows(reports: list[dict]) -> list[dict]:
    return [
        {"snapshot": report["reference_date"], "data_file": report["data_file"], **report["summary"]["overall"]}
        for report in reports
    ]


def metric_rows(reports: list[dict]) -> list[dict]:
    return _summary_rows(reports, "by_metric", "metric")


def category_rows(reports: list[dict]) -> list[dict]:
    return _summary_rows(reports, "by_category", "category")


def verdict_grid(reports: list[dict]) -> list[dict]:
    rows = {}
    for report in reports:
        for case in report["cases"]:
            row = rows.setdefault(case["id"], {"case": case["id"], "category": case["category"], "question": case["question"]})
            row[report["reference_date"]] = case["verdict"]
    return list(rows.values())


def case_records(reports: list[dict]) -> list[dict]:
    records = []
    for report in reports:
        for case in report["cases"]:
            answer = next(
                (m for m in case["metrics"] if m["metric"] in DETERMINISTIC_METRICS and m["applies"]), None
            )
            reasoning = next((m for m in case["metrics"] if m["metric"] == "response_quality"), None)
            records.append({
                **case,
                "snapshot": report["reference_date"],
                "data_file": report["data_file"],
                "answer_metric": answer,
                "reasoning_metric": reasoning,
                "relation": relation(answer, reasoning),
            })
    return records


def relation(answer: dict | None, reasoning: dict | None) -> str:
    """How the deterministic answer verdict and the judge's reasoning verdict relate, in plain words."""
    answer_verdict = answer["verdict"] if answer else None
    reasoning_verdict = reasoning["verdict"] if reasoning else None
    if answer_verdict in (None, "ERROR"):
        return "Not evaluated"
    if reasoning_verdict in (None, "ERROR"):
        return "Reasoning not evaluated"
    if reasoning_verdict == "FLAG":
        return "Reasoning needs review"
    if answer_verdict == reasoning_verdict:
        return "Both passed" if answer_verdict == "PASS" else "Both failed"
    if answer_verdict == "PASS":
        return "Right answer, unsupported reasoning"
    if answer["metric"] == "refusal_correct" and "NOT IN DATA" in answer["reason"]:
        return "Refusal format failed, behaviour compliant"
    return "Wrong answer, grounded reasoning"


def calibration_summary(directory: str | Path) -> dict:
    directory = Path(directory)
    predictions = json.loads((directory / "predictions.json").read_text(encoding="utf-8"))["predictions"]
    judge = {p["id"]: p["judge_verdict"] for p in predictions}
    human = _human_verdicts(directory / "human-review.md")
    summary = {
        "examples": len(predictions),
        "judge_vs_labels": sum(p["agrees"] for p in predictions),
        "judge_vs_human": None,
        "human_matrix": None,
    }
    if human is not None and set(human) == set(judge):
        summary["judge_vs_human"] = sum(human[i] == judge[i] for i in judge)
        summary["human_matrix"] = {
            h: {j: sum(1 for i in judge if human[i] == h and judge[i] == j) for j in JUDGE_VERDICTS}
            for h in JUDGE_VERDICTS
        }
    return summary


def _human_verdicts(worksheet: Path) -> dict[str, str] | None:
    """The completed worksheet's verdicts, or None if it is missing or any verdict is blank or invalid."""
    if not worksheet.is_file():
        return None
    verdicts = {
        cal_id: value.strip().strip('"').strip()
        for cal_id, value in HUMAN_VERDICT.findall(worksheet.read_text(encoding="utf-8"))
    }
    return verdicts if verdicts and all(v in JUDGE_VERDICTS for v in verdicts.values()) else None


def _summary_rows(reports: list[dict], section: str, key: str) -> list[dict]:
    names = list(dict.fromkeys(name for report in reports for name in report["summary"][section]))
    rows = []
    for name in names:
        tallies = [report["summary"][section][name] for report in reports if name in report["summary"][section]]
        row = {key: name, **_with_rate(_sum(tallies))}
        for report in reports:
            if name in report["summary"][section]:
                row[report["reference_date"]] = report["summary"][section][name]["pass_rate"]
        rows.append(row)
    return rows


def _sum(tallies) -> dict:
    total = {"total": 0, **{verdict: 0 for verdict in VERDICTS}}
    for tally in tallies:
        for field in total:
            total[field] += tally[field]
    return total


def _with_rate(tally: dict) -> dict:
    return {**tally, "pass_rate": tally["PASS"] / tally["total"] if tally["total"] else None}
