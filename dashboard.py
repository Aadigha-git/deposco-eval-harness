"""Read-only dashboard over the saved eval reports and calibration results.

Run from the repository root: streamlit run dashboard.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from deposco_evals.dashboard_data import (
    calibration_summary,
    case_records,
    category_rows,
    load_reports,
    metric_rows,
    overall_totals,
    snapshot_rows,
    verdict_grid,
)

ROOT = Path(__file__).resolve().parent
STATUS_STYLE = {
    "PASS": "color: #1B5E3F; background-color: #E3F1EA",
    "FLAG": "color: #7A4300; background-color: #FCEBD3",
    "FAIL": "color: #9F1D16; background-color: #FBE4E1",
    "ERROR": "color: #444444; background-color: #E9ECEF",
}
SPOTLIGHT = {
    "P1": "The listed order IDs are right, but the stated count is wrong: answer_correct fails, the judge passes.",
    "P10": "The answer is right, but the reply filtered on order_date instead of ship_date: only the judge fails it.",
    "P12": "The reply declines the weather question but ends with NOT IN DATA instead of REFUSED: "
    "a refusal-format failure, not an answer to the question.",
}
RATE = st.column_config.ProgressColumn("Pass rate", format="%.0f%%", min_value=0, max_value=100)
TABLE_ROW = 35  # st.dataframe row height in pixels, used to show a table without inner scrolling

st.set_page_config(page_title="Deposco eval results", layout="wide")


@st.cache_data
def load():
    reports = load_reports(ROOT / "reports")
    return reports, case_records(reports), calibration_summary(ROOT / "calibration")


def percent(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """Rates are stored as 0-1 fractions; show them as whole percentages."""
    frame = pd.DataFrame(rows)
    frame[columns] = frame[columns] * 100
    return frame


def status_table(rows: list[dict], status_columns: list[str], **kwargs):
    frame = pd.DataFrame(rows)
    styled = frame.style.map(lambda v: STATUS_STYLE.get(v, ""), subset=status_columns)
    st.dataframe(styled, hide_index=True, width="stretch", **kwargs)


try:
    reports, records, calibration = load()
except (OSError, ValueError) as error:
    st.error(f"Could not load the saved reports: {error}. Run the evals first, for example "
             "`python -m deposco_evals --data data/orders_2026-11-10.csv`.")
    st.stop()

snapshots = [report["reference_date"] for report in reports]
totals = overall_totals(reports)
models = sorted({report["assistant_model"] for report in reports}), sorted({report["judge_model"] for report in reports})

st.html('<div style="height:4px;background:#F48020;border-radius:2px;margin-bottom:0.5rem"></div>')
st.title("Assistant eval results")
st.markdown(
    f"**{totals['PASS']} of {totals['total']} graded cases passed** across {len(reports)} order snapshots "
    f"({', '.join(snapshots)}). The assistant is {', '.join(models[0])}; the judge is {', '.join(models[1])}."
)
st.caption("A read-only view of the saved reports in reports/ and calibration/. Nothing here calls an API or re-grades a reply.")

*status_columns, rate_column = st.columns(5)
for column, status in zip(status_columns, ("PASS", "FLAG", "FAIL", "ERROR")):
    column.metric(status, totals[status])
rate_column.metric("Pass rate", f"{totals['pass_rate']:.0%}")

overview, answer_vs_reasoning, explorer, calibration_tab = st.tabs(
    ["Overview", "Answer vs reasoning", "Case explorer", "Judge calibration"]
)

with overview:
    st.subheader("Every case on every snapshot")
    st.caption("Final case verdict. FAIL wins over ERROR, ERROR over FLAG; PASS needs every applicable metric to pass.")
    grid = verdict_grid(reports)
    status_table(
        [{"case": row["case"], **{s: row.get(s) for s in snapshots}, "category": row["category"], "question": row["question"]} for row in grid],
        snapshots, height=TABLE_ROW * (len(grid) + 1) + 3,
        column_config={"case": "Case", "category": "Category", "question": "Question"},
    )

    st.subheader("Snapshots")
    st.dataframe(
        percent(snapshot_rows(reports), ["pass_rate"])[["snapshot", "data_file", "total", "PASS", "FLAG", "FAIL", "ERROR", "pass_rate"]],
        hide_index=True, width="stretch",
        column_config={"snapshot": "Snapshot (today)", "data_file": "Data file", "total": "Cases", "pass_rate": RATE},
    )

    st.subheader("Metrics")
    st.caption("Pass rate is PASS divided by the cases the metric applies to. FLAG and ERROR never count as passes.")
    st.dataframe(
        percent(metric_rows(reports), ["pass_rate", *snapshots])[["metric", "total", "PASS", "FLAG", "FAIL", "ERROR", "pass_rate", *snapshots]],
        hide_index=True, width="stretch",
        column_config={"metric": "Metric", "total": "Applicable", "pass_rate": RATE,
                       **{s: st.column_config.NumberColumn(s, format="%.0f%%") for s in snapshots}},
    )

    st.subheader("Categories")
    st.caption("Final case verdicts, summed over the snapshots.")
    st.dataframe(
        percent(category_rows(reports), ["pass_rate"])[["category", "total", "PASS", "FLAG", "FAIL", "ERROR", "pass_rate"]],
        hide_index=True, width="stretch", column_config={"category": "Category", "total": "Cases", "pass_rate": RATE},
    )

with answer_vs_reasoning:
    st.markdown(
        "Each case has two independent verdicts. The **answer verdict** comes from code: `answer_correct` checks the final "
        "value, and `refusal_correct` checks the refusal marker on P8 and P12. The **reasoning verdict** comes from the judge "
        "(`response_quality`), which checks grounding and behaviour but never the number. Execution errors are a separate "
        "ERROR status and never a pass."
    )
    for case_id, note in SPOTLIGHT.items():
        rows = [r for r in records if r["id"] == case_id]
        st.subheader(f"{case_id}: {rows[0]['question']}")
        st.caption(note)
        status_table(
            [
                {
                    "Snapshot": r["snapshot"],
                    "Answer verdict": r["answer_metric"]["verdict"],
                    "Reasoning verdict": r["reasoning_metric"]["verdict"],
                    "Final": r["verdict"],
                    "Relation": r["relation"],
                    "Answer reason": r["answer_metric"]["reason"],
                    "Judge reason": r["reasoning_metric"]["reason"],
                }
                for r in rows
            ],
            ["Answer verdict", "Reasoning verdict", "Final"],
        )
    st.caption("The P12 reasons above are the saved baseline wording; newer runs say “output-format noncompliance” instead of “did not refuse”.")

    st.subheader("All cases where the two verdicts differ")
    differing = [r for r in records if r["relation"] not in ("Both passed", "Both failed")]
    status_table(
        [{"Snapshot": r["snapshot"], "Case": r["id"], "Relation": r["relation"],
          "Answer verdict": r["answer_metric"]["verdict"] if r["answer_metric"] else None,
          "Reasoning verdict": r["reasoning_metric"]["verdict"] if r["reasoning_metric"] else None, "Final": r["verdict"]}
         for r in differing],
        ["Answer verdict", "Reasoning verdict", "Final"],
    )

with explorer:
    pick_snapshots, pick_cases, pick_verdicts = st.columns(3)
    chosen_snapshots = pick_snapshots.multiselect("Snapshot", snapshots, default=snapshots)
    case_ids = list(dict.fromkeys(r["id"] for r in records))
    chosen_cases = pick_cases.multiselect("Case", case_ids, placeholder="All cases")
    chosen_verdicts = pick_verdicts.multiselect("Final verdict", ["PASS", "FLAG", "FAIL", "ERROR"], placeholder="All verdicts")
    matching = [
        r for r in records
        if r["snapshot"] in chosen_snapshots
        and (not chosen_cases or r["id"] in chosen_cases)
        and (not chosen_verdicts or r["verdict"] in chosen_verdicts)
    ]
    st.caption(f"{len(matching)} of {len(records)} case results match.")
    if not matching:
        st.info("No case results match these filters. Clear a filter to see more.")
    else:
        status_table(
            [{"Snapshot": r["snapshot"], "Case": r["id"], "Category": r["category"], "Final": r["verdict"],
              "Relation": r["relation"], "Question": r["question"]} for r in matching],
            ["Final"],
        )
        labels = {f"{r['id']} on {r['snapshot']}: {r['verdict']}": r for r in matching}
        chosen = labels[st.selectbox("Inspect a case result", list(labels))]
        expected = chosen["expected"]

        st.subheader(f"{chosen['id']} on {chosen['snapshot']}: {chosen['verdict']}")
        st.markdown(f"**Question:** {chosen['question']}")
        st.markdown(f"**Expected answer:** {expected['accepted']}")
        evidence = [f"Rule: {expected['rule']}"]
        if expected["order_ids"]:
            evidence.append(f"Orders: {', '.join(map(str, expected['order_ids']))}")
        if expected["tallies"]:
            evidence.append("Tallies: " + ", ".join(f"{name} {count}" for name, count in sorted(expected["tallies"].items(), key=lambda kv: (-kv[1], kv[0]))))
        st.markdown("  \n".join(evidence))
        st.markdown("**Assistant response**")
        st.code(chosen["response"] or "No response: the assistant call failed.", language=None, wrap_lines=True)
        st.markdown("**Metric verdicts**")
        status_table(
            [{"Metric": m["metric"], "Verdict": m["verdict"] if m["applies"] else "n/a",
              "Score": "-" if m["score"] is None else f"{m['score']:g}",
              "Threshold": "-" if m["threshold"] is None else f"{m['threshold']:g}", "Reason": m["reason"]}
             for m in chosen["metrics"]],
            ["Verdict"],
        )
        if chosen["judge"]:
            st.markdown(f"**Judge reason:** {chosen['judge']['reason']}")
            st.markdown("**Judge evidence**")
            for item in chosen["judge"]["evidence"] or ["No evidence quoted."]:
                st.code(item, language=None, wrap_lines=True)
        if chosen["error"]:
            st.warning(f"Error: {chosen['error']}")

with calibration_tab:
    st.markdown(
        "Before relying on the judge, 10 replies were graded by hand and compared with the judge's saved verdicts "
        "(one call per example, no retries)."
    )
    first, second, third = st.columns(3)
    first.metric("Calibration examples", calibration["examples"])
    second.metric("Judge agrees with the original labels", f"{calibration['judge_vs_labels']} of {calibration['examples']}")
    if calibration["judge_vs_human"] is None:
        third.metric("Judge agrees with the candidate's review", "Not recorded")
    else:
        third.metric("Judge agrees with the candidate's review", f"{calibration['judge_vs_human']} of {calibration['examples']}")
        st.markdown("**Candidate verdict (rows) against judge verdict (columns)**")
        st.dataframe(pd.DataFrame(calibration["human_matrix"]).T, width="content")
    st.warning(
        "This agreement is preliminary. The original labels were written by the AI coding agent that also wrote the rubric. "
        "The candidate's review hid the labels and judge verdicts, but was not fully blind. Seven of the ten replies are "
        "clear-cut, hand-written cases, each was judged once, and no example covers ties, not-in-data, date boundaries, "
        "or refusing an answerable question. See calibration/human-agreement.md."
    )
