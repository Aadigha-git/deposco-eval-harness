"""Evaluation dashboard: a read-only view of the saved reports and calibration results."""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_pages.common import pill, status_table
from deposco_evals.dashboard_data import (
    VERDICTS,
    calibration_summary,
    case_records,
    category_rows,
    load_reports,
    metric_rows,
    overall_totals,
    snapshot_rows,
    verdict_grid,
)

ROOT = Path(__file__).resolve().parent.parent  # pages run from disk, so this follows the copy being run

BAR_COLOURS = {"PASS": "#6FBF95", "FLAG": "#F2B866", "FAIL": "#E5736A", "ERROR": "#9AA7B2"}
SPOTLIGHT = {
    "P1": "Look for a reply that lists the right orders but states the wrong count: the answer metric checks the count, "
    "the judge checks only that the stated facts are grounded.",
    "P10": "Look for a right answer reached by the wrong method: the answer metric sees only the value, "
    "the judge checks which date column and period the reply used.",
    "P12": "Look for a reply that declines but uses NOT IN DATA instead of REFUSED: refusal_correct fails the marker, "
    "while the judge checks whether the reply actually answered the weather question.",
}
RATE = st.column_config.ProgressColumn("Pass rate", format="%.0f%%", min_value=0, max_value=100)
TABLE_ROW = 35  # st.dataframe row height in pixels, used to show a table without inner scrolling


def percent(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """Rates are stored as 0-1 fractions; show them as whole percentages."""
    frame = pd.DataFrame(rows)
    frame[columns] = frame[columns].astype(float) * 100
    return frame


def verdict_bar(tally: dict, light: bool = False) -> str:
    segments = "".join(
        f'<span style="width:{100 * tally[v] / tally["total"]:.2f}%;background:{BAR_COLOURS[v]}"></span>'
        for v in VERDICTS if tally[v]
    )
    label = ", ".join(f"{tally[v]} {v}" for v in VERDICTS)
    return f'<div class="verdict-bar{" light" if light else ""}" role="img" aria-label="{label}">{segments}</div>'


def verdict_of(metric: dict | None) -> str | None:
    return metric["verdict"] if metric else None


try:
    reports = load_reports(ROOT / "reports")
except (OSError, ValueError) as error:
    st.error(f"Could not load the saved reports: {error}. Run the evals first, for example "
             "`python -m deposco_evals --data data/orders_2026-11-10.csv`.")
    st.stop()
try:
    calibration = calibration_summary(ROOT / "calibration")
except (OSError, ValueError, KeyError):
    calibration = None

records = case_records(reports)
snapshots = [report["reference_date"] for report in reports]
totals = overall_totals(reports)
assistants = ", ".join(sorted({report["assistant_model"] for report in reports}))
judges = ", ".join(sorted({report["judge_model"] for report in reports}))

with st.container(key="hero"):
    st.markdown(
        '<div class="hero-rule"></div>'
        f"<h1>{totals['PASS']} of {totals['total']} cases passed</h1>"
        f"<p>Saved baseline across {len(reports)} order snapshots ({', '.join(snapshots)}). "
        f"{assistants} answers; {judges} judges.</p>"
        f"{verdict_bar(totals)}"
        '<div class="legend">'
        + "".join(f"<span><b>{totals[v]}</b>{v}</span>" for v in VERDICTS)
        + f"<span><b>{totals['pass_rate']:.0%}</b>pass rate</span></div>",
        unsafe_allow_html=True,
    )
st.caption("Read-only: everything on this page comes from reports/ and calibration/. Nothing here calls an API.")

st.subheader("Snapshot comparison")
for column, row in zip(st.columns(len(reports)), snapshot_rows(reports)):
    with column, st.container(border=True, key=f"snapshot-{row['snapshot']}"):
        st.markdown(f"**{row['snapshot']}**")
        st.caption(row["data_file"])
        st.markdown(f'<div class="big-rate">{row["pass_rate"]:.0%}</div>{verdict_bar(row, light=True)}', unsafe_allow_html=True)
        st.caption(f"{row['PASS']} pass, {row['FLAG']} flag, {row['FAIL']} fail, {row['ERROR']} error of {row['total']} cases")

grid_tab, metrics_tab, reasoning_tab, explorer_tab, calibration_tab = st.tabs(
    ["Case grid", "Metrics and categories", "Answer vs reasoning", "Case explorer", "Judge calibration"]
)

with grid_tab:
    st.caption("Final case verdict on each snapshot. FAIL wins over ERROR, ERROR over FLAG; PASS needs every applicable "
               "metric to pass.")
    grid = verdict_grid(reports)
    status_table(
        [{"case": row["case"], **{s: row.get(s) for s in snapshots}, "category": row["category"], "question": row["question"]}
         for row in grid],
        snapshots, height=TABLE_ROW * (len(grid) + 1) + 3,
        column_config={"case": "Case", "category": "Category", "question": "Question"},
    )

with metrics_tab:
    st.markdown("**Metrics.** Pass rate is PASS divided by the cases the metric applies to; FLAG and ERROR never count "
                "as passes.")
    st.dataframe(
        percent(metric_rows(reports), ["pass_rate", *snapshots])[["metric", "total", *VERDICTS, "pass_rate", *snapshots]],
        hide_index=True, width="stretch",
        column_config={"metric": "Metric", "total": "Applicable", "pass_rate": RATE,
                       **{s: st.column_config.NumberColumn(s, format="%.0f%%") for s in snapshots}},
    )
    st.markdown("**Categories.** Final case verdicts, summed over the snapshots.")
    st.dataframe(
        percent(category_rows(reports), ["pass_rate"])[["category", "total", *VERDICTS, "pass_rate"]],
        hide_index=True, width="stretch", column_config={"category": "Category", "total": "Cases", "pass_rate": RATE},
    )

with reasoning_tab:
    st.markdown(
        "Each case has two independent verdicts. The **answer verdict** comes from code: `answer_correct` checks the final "
        "value, and `refusal_correct` checks the refusal marker on P8 and P12. The **reasoning verdict** comes from the judge "
        "(`response_quality`), which checks grounding and behaviour but never the number. Execution errors are a separate "
        "ERROR status and never a pass."
    )
    for case_id, note in SPOTLIGHT.items():
        rows = [r for r in records if r["id"] == case_id]
        if not rows:
            continue
        st.markdown(f"#### {case_id}: {rows[0]['question']}")
        st.caption(note)
        status_table(
            [
                {
                    "Snapshot": r["snapshot"],
                    "Answer verdict": verdict_of(r["answer_metric"]),
                    "Reasoning verdict": verdict_of(r["reasoning_metric"]),
                    "Final": r["verdict"],
                    "Relation": r["relation"],
                    "Answer reason": r["answer_metric"]["reason"] if r["answer_metric"] else None,
                    "Judge reason": r["reasoning_metric"]["reason"] if r["reasoning_metric"] else None,
                }
                for r in rows
            ],
            ["Answer verdict", "Reasoning verdict", "Final"],
        )
    st.caption("Saved P12 reasons may read “did not refuse”: the reports predate the wording “output-format noncompliance”.")
    st.markdown("#### All cases where the two verdicts differ")
    differing = [r for r in records if r["relation"] not in ("Both passed", "Both failed")]
    status_table(
        [{"Snapshot": r["snapshot"], "Case": r["id"], "Relation": r["relation"], "Answer verdict": verdict_of(r["answer_metric"]),
          "Reasoning verdict": verdict_of(r["reasoning_metric"]), "Final": r["verdict"]} for r in differing],
        ["Answer verdict", "Reasoning verdict", "Final"],
    )

with explorer_tab:
    pick_snapshots, pick_cases, pick_verdicts = st.columns(3)
    chosen_snapshots = pick_snapshots.multiselect("Snapshot", snapshots, default=snapshots)
    chosen_cases = pick_cases.multiselect("Case", list(dict.fromkeys(r["id"] for r in records)), placeholder="All cases")
    chosen_verdicts = pick_verdicts.multiselect("Final verdict", list(VERDICTS), placeholder="All verdicts")
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
        with st.container(border=True):
            st.markdown(f"#### {chosen['id']} on {chosen['snapshot']} {pill(chosen['verdict'])}", unsafe_allow_html=True)
            st.markdown(f"**Question:** {chosen['question']}")
            st.markdown(f"**Expected answer:** {expected['accepted']}")
            evidence = [f"Rule: {expected['rule']}"]
            if expected["order_ids"]:
                evidence.append(f"Orders: {', '.join(map(str, expected['order_ids']))}")
            if expected["tallies"]:
                ordered = sorted(expected["tallies"].items(), key=lambda item: (-item[1], item[0]))
                evidence.append("Tallies: " + ", ".join(f"{name} {count}" for name, count in ordered))
            st.markdown("  \n".join(evidence))
            st.markdown("**Assistant response** (saved)")
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
    if calibration is None:
        st.info("No calibration results found in calibration/. Run `python -m deposco_evals.calibration` to create them.")
    else:
        examples = calibration["examples"]
        st.markdown(
            f"Before relying on the judge, {examples} replies were graded by hand and compared with the judge's saved "
            "verdicts (one call per example, no retries)."
        )
        first, second, third = st.columns(3)
        first.metric("Calibration examples", examples)
        second.metric("Judge agrees with the original labels", f"{calibration['judge_vs_labels']} of {examples}")
        if calibration["judge_vs_human"] is None:
            third.metric("Judge agrees with the candidate's review", "Not recorded")
        else:
            third.metric("Judge agrees with the candidate's review", f"{calibration['judge_vs_human']} of {examples}")
            st.markdown("**Candidate verdict (rows) against judge verdict (columns)**")
            st.dataframe(pd.DataFrame(calibration["human_matrix"]).T, width="content")
        st.warning(
            "This agreement is preliminary. The original labels were written by the AI coding agent that also wrote the "
            "rubric. The candidate's review hid the labels and judge verdicts, but was not fully blind. Most replies are "
            "clear-cut, hand-written cases, each was judged once, and no example covers ties, not-in-data, date boundaries, "
            "or refusing an answerable question. See calibration/human-agreement.md."
        )
