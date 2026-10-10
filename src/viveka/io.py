"""Read Excel / CSV / JSON rows into a canonical DataFrame, and write predictions."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from viveka.align import Mapping, align
from viveka.output import Prediction

HEADER_SCAN_ROWS = 15


def _detect_header(raw: pd.DataFrame) -> int:
    """Pick the row in the top of a sheet with the most non-empty text cells."""
    best_row, best_count = 0, -1
    for i in range(min(HEADER_SCAN_ROWS, len(raw))):
        row = raw.iloc[i]
        count = sum(isinstance(v, str) and v.strip() != "" for v in row)
        if count > best_count:
            best_row, best_count = i, count
    return best_row


def _dedupe(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for name in headers:
        n = seen.get(name, 0)
        out.append(name if n == 0 else f"{name}.{n}")
        seen[name] = n + 1
    return out


def _frame_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if raw.empty:
        return raw
    h = _detect_header(raw)
    headers = [str(c).strip() if pd.notna(c) else f"column_{j}" for j, c in enumerate(raw.iloc[h])]
    frame = raw.iloc[h + 1 :].copy()
    frame.columns = _dedupe(headers)
    return frame.dropna(how="all").reset_index(drop=True)


def read_rows(path: str | Path) -> pd.DataFrame:
    """Read every sheet (xlsx), a CSV or a JSON array; return raw-header rows with provenance."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None, header=None, engine="calamine")
        frames = []
        for name, raw in sheets.items():
            frame = _frame_from_raw(raw)
            if not frame.empty:
                frames.append(frame.assign(_sheet=name))
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    elif suffix == ".csv":
        df = _frame_from_raw(pd.read_csv(path, header=None, dtype=object))
        df["_sheet"] = path.stem
    elif suffix in {".json", ".jsonl"}:
        df = pd.read_json(path, lines=suffix == ".jsonl", dtype=False)
        df["_sheet"] = path.stem
    else:
        raise ValueError(f"Unsupported file type: {suffix}")
    df.insert(0, "_row_id", range(len(df)))
    return df


def to_canonical(
    df: pd.DataFrame, overrides: dict[str, str] | None = None
) -> tuple[pd.DataFrame, list[Mapping]]:
    """Rename mapped columns to canonical names; keep unmapped ones under an `extra:` prefix."""
    data_cols = [c for c in df.columns if not str(c).startswith("_")]
    mappings = align([str(c) for c in data_cols], overrides)
    rename = {m.header: (m.field or f"extra:{m.header}") for m in mappings}
    return df.rename(columns=rename), mappings


def write_predictions(preds: list[Prediction], path: str | Path, fmt: str = "minimal") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "minimal":
        payload = [p.minimal() for p in preds]
    elif fmt == "full":
        payload = [p.model_dump(mode="json") for p in preds]
    else:
        raise ValueError(f"Unknown format: {fmt}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_table(raw: pd.DataFrame, preds: list[Prediction], path: str | Path) -> None:
    """Return the original sheet with prediction columns appended, as CSV or XLSX."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = raw.copy()
    out["voucher_type"] = [p.voucher_type for p in preds]
    out["confidence"] = [p.confidence for p in preds]
    out["needs_review"] = [p.needs_review for p in preds]
    out["explanation"] = [p.explanation for p in preds]
    if path.suffix.lower() == ".xlsx":
        out.to_excel(path, index=False, engine="openpyxl")
    else:
        out.to_csv(path, index=False)
