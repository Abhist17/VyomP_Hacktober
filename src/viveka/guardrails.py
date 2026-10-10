"""Hard accounting constraints. A label that breaks one is demoted and the reason logged.

TODO(block 3): cross-row checks over the document-link graph (PO -> GRN -> Purchase).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from viveka.labels import FALLBACK, LABEL_INDEX
from viveka.signals import EvidenceCard

Constraint = tuple[str, Callable[[EvidenceCard], bool], str]

# Demotions of labels below this probability are applied silently (smoothing mass only).
REPORT_THRESHOLD = 0.05

CONSTRAINTS: list[Constraint] = [
    (
        "Contra",
        lambda c: c["both_legs_own_cash_bank"] is False,
        "Contra requires both legs to be the company's own cash or bank accounts",
    ),
    ("Attendance", lambda c: c["has_money"] is True, "Attendance carries no money"),
    (
        "Physical Stock",
        lambda c: c["stock_count"] is False,
        "Physical Stock requires a counted quantity",
    ),
    (
        "Salary / Payroll",
        lambda c: c["payroll_components"] is False and c["employee_present"] is False,
        "Salary / Payroll requires an employee or a pay breakdown",
    ),
]


def apply(probs: np.ndarray, card: EvidenceCard) -> tuple[np.ndarray, list[str]]:
    probs = probs.copy()
    reasons = []
    for label, violated, reason in CONSTRAINTS:
        i = LABEL_INDEX[label]
        if probs[i] > 0 and violated(card):
            if probs[i] >= REPORT_THRESHOLD:
                reasons.append(f"{label} demoted: {reason}")
            probs[i] = 0.0
    if probs.sum() <= 0:
        probs[LABEL_INDEX[FALLBACK]] = 1.0
    return probs / probs.sum(), reasons
