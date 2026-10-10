"""Smoke and metamorphic tests on the fictional sample (README section 2.5)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from viveka.cli import main
from viveka.evaluate import evaluate
from viveka.io import read_rows
from viveka.labels import LABELS, flip
from viveka.pipeline import classify

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SAMPLE = EXAMPLES / "sample_transactions.csv"
GOLD = EXAMPLES / "sample_gold.csv"
COMPANY = "27AAACK1234M1ZL"


@pytest.fixture(scope="module")
def raw() -> pd.DataFrame:
    return read_rows(SAMPLE)


def _labels(preds):
    return {p.invoice_number: p.voucher_type for p in preds}


def test_one_valid_label_per_row(raw):
    preds = classify(raw)
    assert len(preds) == len(raw)
    assert all(p.voucher_type in LABELS for p in preds)
    assert [p.row_id for p in preds] == list(range(len(raw)))


def test_deterministic(raw):
    assert _labels(classify(raw)) == _labels(classify(raw))


def test_keyword_trap_is_contra(raw):
    """'Fund transfer for salary' between two own bank accounts."""
    assert _labels(classify(raw))["CTR/12"] == "Contra"


def test_perspective_swap_flips_directional_labels(raw):
    base = _labels(classify(raw, company_gstin=COMPANY))
    swapped = _labels(classify(raw, company_gstin="24AABCN5678P1ZT"))  # Narmada's books
    for inv in ("KF/S/101", "CN/2026/018", "DC/45"):
        assert swapped[inv] == flip(base[inv]), inv


def test_header_rename_and_column_shuffle_invariance(raw):
    base = _labels(classify(raw))
    renamed = raw.rename(
        columns={"Invoice No": "Bill No", "Narration": "Remarks", "Qty": "Quantity"}
    )
    shuffled = renamed[[renamed.columns[0], *reversed(renamed.columns[1:])]]
    assert _labels(classify(shuffled)) == base


def test_row_order_invariance(raw):
    base = _labels(classify(raw))
    shuffled = raw.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuffled["_row_id"] = range(len(shuffled))
    assert _labels(classify(shuffled)) == base


def test_cli_predict_and_evaluate(tmp_path):
    pred = tmp_path / "pred.json"
    assert main(["predict", str(SAMPLE), "--out", str(pred)]) == 0
    payload = json.loads(pred.read_text())
    assert set(payload[0]) == {"invoice_number", "voucher_type"}
    report = evaluate(pred, GOLD)
    assert report["join_key"] == "invoice_number"
    assert report["rows"]["matched"] == len(payload)
    assert 0.0 <= report["macro_f1"] <= 1.0
