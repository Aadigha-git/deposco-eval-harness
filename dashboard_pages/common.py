"""Status styling shared by the two dashboard pages."""

import pandas as pd
import streamlit as st

STATUS_STYLE = {
    "PASS": "color: #1B5E3F; background-color: #E3F1EA",
    "FLAG": "color: #7A4300; background-color: #FCEBD3",
    "FAIL": "color: #9F1D16; background-color: #FBE4E1",
    "ERROR": "color: #444444; background-color: #E9ECEF",
}


def pill(verdict: str | None) -> str:
    """An inline status label; the word is always shown, so colour is never the only signal."""
    return f'<span class="pill pill-{verdict}">{verdict}</span>' if verdict in STATUS_STYLE else "n/a"


def status_table(rows: list[dict], status_columns: list[str], **kwargs):
    frame = pd.DataFrame(rows)
    styled = frame.style.map(lambda v: STATUS_STYLE.get(v, ""), subset=status_columns)
    st.dataframe(styled, hide_index=True, width="stretch", **kwargs)
