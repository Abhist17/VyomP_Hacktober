"""REST API (FastAPI). Requires the `api` extra."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from viveka import __version__
from viveka.io import read_rows
from viveka.labels import FAMILIES
from viveka.output import Prediction
from viveka.pipeline import classify, run
from viveka.policy import load_policy
from viveka.workbench import payload

WEB_DIR = Path(__file__).parent / "web"
_SAMPLE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "examples" / "sample_transactions.csv",
    Path.cwd() / "examples" / "sample_transactions.csv",
)

app = FastAPI(title="Viveka", version=__version__)
POLICY = load_policy()


class RowsRequest(BaseModel):
    rows: list[dict[str, Any]]
    company_gstin: str | None = None
    company_name: str | None = None
    mode: str = "accurate"


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.insert(0, "_row_id", range(len(df)))
    return df


async def _read_upload(file: UploadFile) -> pd.DataFrame:
    suffix = Path(file.filename or "upload.xlsx").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        try:
            return read_rows(tmp.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/classify", response_model=list[Prediction])
async def classify_file(file: Annotated[UploadFile, File()]) -> list[Prediction]:
    return classify(await _read_upload(file), POLICY)


@app.post("/v1/workbench")
async def workbench_file(
    file: Annotated[UploadFile, File()],
    company_gstin: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Predictions plus rows, context and column mappings, for the web workbench."""
    raw = await _read_upload(file)
    result = run(raw, POLICY, company_gstin=company_gstin or None)
    return payload(result, file.filename or "upload")


@app.get("/v1/workbench/sample")
def workbench_sample(company_gstin: str | None = None) -> dict[str, Any]:
    path = next((p for p in _SAMPLE_CANDIDATES if p.is_file()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="Sample file not found in examples/")
    return payload(run(read_rows(path), POLICY, company_gstin=company_gstin), path.name)


@app.post("/v1/classify/rows", response_model=list[Prediction])
def classify_rows(req: RowsRequest) -> list[Prediction]:
    return classify(_frame(req.rows), POLICY, req.mode, req.company_gstin, req.company_name)


@app.post("/v1/classify/row", response_model=Prediction)
def classify_row(req: RowsRequest) -> Prediction:
    # TODO(block 6): add `clarifying_question` and the label each answer leads to.
    if len(req.rows) != 1:
        raise HTTPException(status_code=400, detail="Send exactly one row")
    return classify(_frame(req.rows), POLICY, req.mode, req.company_gstin, req.company_name)[0]


@app.post("/v1/feedback", status_code=501)
def feedback() -> dict[str, str]:
    # TODO(block 5): store the correction in precedent memory.
    return {"detail": "Not implemented yet"}


@app.get("/v1/labels")
def labels() -> list[dict[str, Any]]:
    """The 27 labels grouped by playbook family."""
    return [{"name": name, "labels": list(group)} for name, group in FAMILIES]


@app.get("/v1/model-card")
def model_card() -> dict[str, Any]:
    return {
        "viveka_version": __version__,
        "policy_version": POLICY.version,
        "slm": POLICY.slm,
        "evaluation": None,
    }


# Mounted last so the API routes above take precedence.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
