"""Evaluation report: accuracy, macro-F1, per-class table, confusion matrix, pair scoreboard.

TODO(block 6): calibration (ECE, Brier, reliability), selective accuracy, metamorphic suite,
latency / memory figures per run mode.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from viveka import __version__
from viveka.io import read_rows
from viveka.labels import CONFUSABLE_PAIRS, LABELS
from viveka.normalise import is_blank
from viveka.schema import normalise_header

GOLD_COLUMNS = ("voucher type", "voucher_type", "vouchertype", "label", "category", "true label")
INVOICE_COLUMNS = ("invoice number", "invoice no", "invoice_number")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _doc_key(value: object) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def load_predictions(path: str | Path) -> pd.DataFrame:
    df = pd.DataFrame(json.loads(Path(path).read_text(encoding="utf-8")))
    if "row_id" not in df:
        df["row_id"] = range(len(df))
    df["invoice_number"] = df["invoice_number"].map(_doc_key)
    return df[["row_id", "invoice_number", "voucher_type"]]


def load_gold(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".json":
        df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    else:
        df = read_rows(path)
    by_norm = {normalise_header(c): c for c in df.columns}
    label_col = next(
        (by_norm[c] for c in map(normalise_header, GOLD_COLUMNS) if c in by_norm), None
    )
    if label_col is None:
        raise ValueError(f"No voucher-type column in {path}; expected one of {GOLD_COLUMNS}")
    inv_col = next(
        (by_norm[c] for c in map(normalise_header, INVOICE_COLUMNS) if c in by_norm), None
    )
    return pd.DataFrame(
        {
            "row_id": range(len(df)),
            "invoice_number": df[inv_col].map(_doc_key) if inv_col else None,
            "voucher_type": df[label_col].astype(str).str.strip(),
        }
    )


def join(pred: pd.DataFrame, gold: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Join on invoice_number when it is present and unique on both sides, else on row order."""
    usable = all(
        df["invoice_number"].notna().all() and df["invoice_number"].is_unique for df in (pred, gold)
    )
    if usable:
        merged = gold.merge(pred, on="invoice_number", suffixes=("_gold", "_pred"))
        return merged, "invoice_number"
    return gold.merge(pred, on="row_id", suffixes=("_gold", "_pred")), "row_id"


def evaluate(pred_path: str | Path, gold_path: str | Path) -> dict:
    pred, gold = load_predictions(pred_path), load_gold(gold_path)
    merged, key = join(pred, gold)
    y_true, y_pred = merged["voucher_type_gold"], merged["voucher_type_pred"]
    present = [label for label in LABELS if label in set(y_true) | set(y_pred)]

    pairs = {}
    for name, members in CONFUSABLE_PAIRS.items():
        mask = y_true.isin(members)
        n = int(mask.sum())
        errors = int((y_true[mask] != y_pred[mask]).sum())
        pairs[name] = {"rows": n, "errors": errors, "error_rate": errors / n if n else None}

    return {
        "viveka_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": {
            "predictions": {"path": str(pred_path), "sha256": _sha256(Path(pred_path))},
            "gold": {"path": str(gold_path), "sha256": _sha256(Path(gold_path))},
        },
        "join_key": key,
        "rows": {"gold": len(gold), "predictions": len(pred), "matched": len(merged)},
        "unknown_gold_labels": sorted(set(y_true) - set(LABELS)),
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, labels=present, average="macro", zero_division=0),
        "weighted_f1": f1_score(
            y_true, y_pred, labels=present, average="weighted", zero_division=0
        ),
        "per_class": classification_report(
            y_true, y_pred, labels=present, output_dict=True, zero_division=0
        ),
        "confusion_matrix": {
            "labels": present,
            "matrix": confusion_matrix(y_true, y_pred, labels=present).tolist(),
        },
        "confusable_pairs": pairs,
    }


def write_report(report: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Viveka evaluation report",
        "",
        f"- Rows matched: {report['rows']['matched']} (join on `{report['join_key']}`)",
        f"- Accuracy: {report['accuracy']:.4f}",
        f"- Macro-F1: {report['macro_f1']:.4f}",
        f"- Weighted F1: {report['weighted_f1']:.4f}",
        "",
        "## Per class",
        "",
        "| Voucher type | Precision | Recall | F1 | Support |",
        "|---|---|---|---|---|",
    ]
    for label in report["confusion_matrix"]["labels"]:
        m = report["per_class"].get(label)
        if m:
            lines.append(
                f"| {label} | {m['precision']:.3f} | {m['recall']:.3f} | "
                f"{m['f1-score']:.3f} | {int(m['support'])} |"
            )
    lines += ["", "## Confusable pairs", "", "| Pair | Rows | Error rate |", "|---|---|---|"]
    for name, p in report["confusable_pairs"].items():
        rate = "n/a" if p["error_rate"] is None else f"{p['error_rate']:.3f}"
        lines.append(f"| {name} | {p['rows']} | {rate} |")
    path = out_dir / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
