"""Assistant playground: ask the live assistant one question about one snapshot. Nothing is saved."""

import html
from pathlib import Path

import streamlit as st

from dashboard_pages.common import pill
from deposco_evals.cases import load_cases
from deposco_evals.dashboard_data import case_records, load_reports
from deposco_evals.llm import LLMError, config_from_env, make_complete
from deposco_evals.playground import ask_live
from deposco_evals.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parent.parent  # pages run from disk, so this follows the copy being run

GOLDEN, CUSTOM = "Golden case", "Your own question"

st.html('<div class="hero-rule"></div>')
st.title("Assistant playground")
st.markdown(
    "Ask the live assistant a question about one order snapshot. Live replies are graded on the spot when the question "
    "is a golden case, but they are never saved and never change the reports on the evaluation dashboard."
)

try:
    config = config_from_env()
except LLMError:
    config = None
data_files = sorted((ROOT / "data").glob("orders_*.csv"))
cases = load_cases()

if config is None:
    st.info(
        "Live runs need a Gemini API key, and none is set. Export `GEMINI_API_KEY` in the shell that starts the "
        "dashboard (for example `set -a; source .env; set +a`), then restart it. The evaluation dashboard works without a key."
    )
if not data_files:
    st.warning("No `orders_YYYY-MM-DD.csv` files found in data/. Add a snapshot to ask questions about it.")
    st.stop()

ask_column, output_column = st.columns([1, 1.35], gap="large")

with ask_column, st.container(border=True):
    st.markdown("#### Question")
    data_file = st.selectbox("Snapshot", data_files, index=len(data_files) - 1, format_func=lambda p: p.name)
    mode = st.radio("Ask", [GOLDEN, CUSTOM], horizontal=True, label_visibility="collapsed")
    if mode == GOLDEN:
        case = st.selectbox("Golden case", cases, format_func=lambda c: f"{c.id}: {c.question}")
        question = case.question
    else:
        question = st.text_area("Question", placeholder="For example: How many orders shipped by FedEx this month?").strip()
    if config:
        st.caption(f"Model: {config.assistant_model}. Today is taken from the file name.")
    run = st.button("Run assistant", type="primary", disabled=config is None or not question, width="stretch")

if run:
    try:
        snapshot = load_snapshot(data_file)
        with output_column, st.spinner(f"Asking {config.assistant_model}…"):
            st.session_state.live = (snapshot, ask_live(snapshot, question, cases, make_complete(config), config.assistant_model))
        st.session_state.pop("live_error", None)
    except (LLMError, ValueError, OSError) as error:  # SnapshotError and UnicodeDecodeError are ValueErrors
        st.session_state.live_error = str(error)
        st.session_state.pop("live", None)

with output_column:
    if "live_error" in st.session_state:
        st.error(f"The live run failed: {st.session_state.live_error}")
    elif "live" not in st.session_state:
        with st.container(border=True):
            st.markdown("#### Live assistant output")
            st.markdown("Choose a snapshot and a question, then select **Run assistant**. The reply, its parsed "
                        "`Answer:` line and, for golden cases, the expected answer and metric verdicts appear here.")
    else:
        snapshot, result = st.session_state.live
        if result.question != question or snapshot.source_name != data_file.name:
            st.warning("This result is for an earlier question or snapshot. Select **Run assistant** to ask the current one.")
        with st.container(key="live-output"):
            st.markdown(f'<span class="source-tag source-live">Live run on {snapshot.source_name}, not saved</span>',
                        unsafe_allow_html=True)
            st.markdown(f"**Question:** {result.question}")
            st.code(result.reply, language=None, wrap_lines=True)
            if result.answer is not None:
                st.markdown(f'**Parsed answer**<div class="answer-value">{html.escape(result.answer)}</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown("**Parsed answer:** none, the reply has no final `Answer:` line")
            if result.case:
                st.markdown(f"**Golden case {result.case.id}.** Expected answer: {result.expected.accepted}")
                for metric in result.metrics:
                    st.markdown(f"{pill(metric.verdict)} `{metric.metric}`: {html.escape(metric.reason)}",
                                unsafe_allow_html=True)
                st.caption("Only the deterministic metrics run here; the judge is not called in the playground.")
            else:
                st.caption("Not a golden case, so there is no expected answer to compare with.")

        saved = None
        if result.case:
            try:
                saved = next((r for r in case_records(load_reports(ROOT / "reports"))
                              if r["id"] == result.case.id and r["snapshot"] == snapshot.today.isoformat()), None)
            except (OSError, ValueError):
                saved = None
        if saved:
            with st.container(key="saved-baseline"):
                st.markdown('<span class="source-tag source-saved">Saved baseline report</span>', unsafe_allow_html=True)
                saved_answer = saved["answer_metric"]["verdict"] if saved["answer_metric"] else None
                st.markdown(f"The committed report for {result.case.id} on {snapshot.source_name} has saved answer verdict "
                            f"{pill(saved_answer)} and final verdict {pill(saved['verdict'])}.", unsafe_allow_html=True)
                st.caption("Compare the live check with the saved answer verdict: the final verdict also counts the "
                           "judge's reasoning verdict, which the playground does not run.")
                with st.expander("Saved reply from the baseline run"):
                    st.code(saved["response"] or "No response: the assistant call failed.", language=None, wrap_lines=True)
