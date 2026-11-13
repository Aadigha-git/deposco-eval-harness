"""Deposco evaluation console: the saved eval results, plus a live assistant playground.

Run from the repository root: streamlit run dashboard.py
"""

import streamlit as st

st.set_page_config(page_title="Deposco evaluation console", layout="wide", initial_sidebar_state="expanded")

st.html("""
<style>
.block-container { padding-top: 4.5rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.01em; }
.st-key-hero { background: linear-gradient(135deg, #24323D 0%, #2D4150 100%); border-radius: 14px;
  padding: 1.6rem 2rem 1.4rem; animation: rise 0.35s ease-out both; }
.st-key-hero p, .st-key-hero h1 { color: #F3F7F9; }
.st-key-hero h1 { font-size: 2.4rem; margin: 0 0 0.25rem; }
.hero-rule { width: 3rem; height: 3px; background: #F48020; border-radius: 2px; margin-bottom: 0.9rem; }
.verdict-bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: #3B4E5D; margin: 1rem 0 0.6rem; }
.verdict-bar span { display: block; height: 100%; }
.verdict-bar.light { background: #E2ECF4; height: 8px; margin: 0.6rem 0 0.5rem; }
.legend { display: flex; flex-wrap: wrap; gap: 1.25rem; color: #D9E4ED; font-size: 0.95rem; }
.legend b { color: #FFFFFF; font-size: 1.15rem; margin-right: 0.3rem; }
[class*="st-key-snapshot-"] { border-top: 3px solid #F48020; border-radius: 10px; }
.answer-value { font-family: Archivo, sans-serif; font-size: 2rem; font-weight: 600; color: #24323D; }
.big-rate { font-family: Archivo, sans-serif; font-size: 2.2rem; font-weight: 600; color: #24323D; line-height: 1.1; }
.pill { display: inline-block; padding: 0.05rem 0.55rem; border-radius: 999px; font-weight: 600; font-size: 0.85rem; }
.pill-PASS { color: #1B5E3F; background: #E3F1EA; } .pill-FLAG { color: #7A4300; background: #FCEBD3; }
.pill-FAIL { color: #9F1D16; background: #FBE4E1; } .pill-ERROR { color: #444444; background: #E9ECEF; }
.source-tag { display: inline-block; padding: 0.1rem 0.6rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600; }
.source-live { color: #1F5F99; background: #E2ECF4; } .source-saved { color: #444444; background: #EEF1F4; }
.st-key-live-output { border-left: 4px solid #4797D8; padding-left: 1rem; animation: rise 0.3s ease-out both; }
.st-key-saved-baseline { border-left: 4px solid #CCCCCC; padding-left: 1rem; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .st-key-hero, .st-key-live-output { animation: none; } }
</style>
""")

st.sidebar.markdown("### Evaluation console")
st.sidebar.caption("Deposco orders assistant. Saved baseline results and a live playground.")

st.navigation(
    [
        st.Page("dashboard_pages/evaluation.py", title="Evaluation dashboard", default=True),
        st.Page("dashboard_pages/playground.py", title="Assistant playground"),
    ],
    position="sidebar",
).run()
