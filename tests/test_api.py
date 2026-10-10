from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from viveka.api import app  # noqa: E402
from viveka.labels import LABELS  # noqa: E402

client = TestClient(app)

ROW = {
    "Invoice No": "CTR/12",
    "Debit Account": "SBI Current A/c 4567",
    "Credit Account": "HDFC Current A/c 5678",
    "Total": "2,50,000.00",
    "Mode": "NEFT",
    "Narration": "Fund transfer for salary disbursement",
}


def test_classify_row():
    r = client.post("/v1/classify/row", json={"rows": [ROW]})
    assert r.status_code == 200
    body = r.json()
    assert body["voucher_type"] == "Contra"
    assert body["invoice_number"] == "CTR/12"


def test_classify_rows_returns_valid_labels():
    r = client.post("/v1/classify/rows", json={"rows": [ROW, {"Narration": "misc"}]})
    assert r.status_code == 200
    assert [p["voucher_type"] in LABELS for p in r.json()] == [True, True]


def test_model_card():
    assert client.get("/v1/model-card").json()["policy_version"].startswith("policy-")


def test_workbench_sample_payload():
    body = client.get("/v1/workbench/sample").json()
    assert body["company"]["gstin"] == "27AAACK1234M1ZL"
    assert body["company"]["name"] == "Kaveri Fabricators Pvt Ltd"
    assert len(body["rows"]) == len(body["predictions"]) == 18
    assert sorted(lbl for f in body["families"] for lbl in f["labels"]) == sorted(LABELS)
    contra = next(r for r in body["rows"] if r["number"] == "CTR/12")
    assert contra["amount"] == 250000.0


def test_workbench_upload_respects_whose_books():
    sample = Path(__file__).resolve().parents[1] / "examples" / "sample_transactions.csv"
    with sample.open("rb") as fh:
        r = client.post(
            "/v1/workbench",
            files={"file": ("day.csv", fh, "text/csv")},
            data={"company_gstin": "24AABCN5678P1ZT"},
        )
    body = r.json()
    assert body["company"]["how"] == "profile"
    first = body["predictions"][0]
    assert (first["invoice_number"], first["voucher_type"]) == ("KF/S/101", "Purchase")


def test_web_app_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "app.js" in r.text
