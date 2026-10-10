"""Upload-and-inspect web app. Run: streamlit run apps/streamlit_app.py

TODO(block 5): column-mapping confirmation, row inspector, review queue, evaluation tab.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from viveka.io import read_rows
from viveka.pipeline import classify
from viveka.policy import load_policy

st.set_page_config(page_title="Viveka", layout="wide")
st.title("Viveka · voucher classification")

upload = st.file_uploader("Transactions (.xlsx or .csv)", type=["xlsx", "csv"])
company_gstin = st.text_input("Company GSTIN (optional; inferred from the file if blank)")

if upload:
    with tempfile.NamedTemporaryFile(suffix=Path(upload.name).suffix) as tmp:
        tmp.write(upload.getvalue())
        tmp.flush()
        raw = read_rows(tmp.name)
    preds = classify(raw, load_policy(), company_gstin=company_gstin or None)
    table = pd.DataFrame(
        {
            "row": [p.row_id for p in preds],
            "invoice_number": [p.invoice_number for p in preds],
            "voucher_type": [p.voucher_type for p in preds],
            "confidence": [p.confidence for p in preds],
            "needs_review": [p.needs_review for p in preds],
            "explanation": [p.explanation for p in preds],
        }
    )
    only_review = st.checkbox("Show only rows that need review")
    st.dataframe(table[table.needs_review] if only_review else table, use_container_width=True)
    st.download_button(
        "Download minimal JSON",
        json.dumps([p.minimal() for p in preds], ensure_ascii=False, indent=2),
        file_name="predictions.json",
        mime="application/json",
    )
