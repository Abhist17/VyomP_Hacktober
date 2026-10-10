"""Versioned labelling policy, loaded from TOML."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Repo checkout first, then the working directory (Docker image, non-editable installs).
_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "policies" / "default.toml",
    Path.cwd() / "policies" / "default.toml",
)


def default_policy_path() -> Path:
    env = os.environ.get("VIVEKA_POLICY")
    if env:
        return Path(env)
    return next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])


@dataclass(frozen=True)
class Policy:
    version: str
    whose_books: str = "inferred"
    paid_expense_bill: str = "Expense"
    salary_bank_transfer: str = "Salary / Payroll"
    sez_or_deemed_export: str = "Export"
    auto_accept_threshold: float = 0.90
    coverage: float = 0.95
    temperature: float = 1.0
    pooling: str = "linear"
    fast_threshold: float = 0.90
    weights: dict[str, float] = field(default_factory=dict)
    slm: dict[str, Any] = field(default_factory=dict)
    sentinel: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def weight(self, source: str) -> float:
        return float(self.weights.get(source, 1.0))


def load_policy(path: str | Path | None = None) -> Policy:
    path = Path(path) if path else default_policy_path()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    conv = data.get("conventions", {})
    dec = data.get("decision", {})
    return Policy(
        version=data["version"],
        whose_books=data.get("perspective", {}).get("whose_books", "inferred"),
        paid_expense_bill=conv.get("paid_expense_bill", "Expense"),
        salary_bank_transfer=conv.get("salary_bank_transfer", "Salary / Payroll"),
        sez_or_deemed_export=conv.get("sez_or_deemed_export", "Export"),
        auto_accept_threshold=float(dec.get("auto_accept_threshold", 0.90)),
        coverage=float(dec.get("coverage", 0.95)),
        temperature=float(dec.get("temperature", 1.0)),
        pooling=str(dec.get("pooling", "linear")),
        fast_threshold=float(dec.get("fast_threshold", 0.90)),
        weights={k: float(v) for k, v in data.get("opinions", {}).items()},
        slm=dict(data.get("slm", {})),
        sentinel=dict(data.get("sentinel", {})),
        raw=data,
    )
