"""Labelling functions over the evidence card.

They serve twice: as weak-supervision sources for training labels, and as the
always-available P0 opinion so the pipeline emits a valid file before the SLM is loaded.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np

from viveka.context import Context
from viveka.labels import FALLBACK, LABEL_INDEX, LABELS, PRECEDENCE, RANK
from viveka.policy import Policy
from viveka.signals import EvidenceCard

Vote = tuple[str, float]
LF = Callable[[EvidenceCard, Policy], list[Vote]]

LABELLING_FUNCTIONS: list[tuple[str, LF]] = []
SMOOTHING = 0.005


def lf(fn: LF) -> LF:
    LABELLING_FUNCTIONS.append((fn.__name__, fn))
    return fn


def directional(
    card: EvidenceCard, if_seller: str, if_buyer: str, w: float, default: str | None = None
) -> list[Vote]:
    """Resolve a direction-dependent pair from whose books these are.

    When the perspective is unknown, vote for `default` (the document's natural direction)
    or split the weight evenly.
    """
    seller, buyer = card["company_is_seller"], card["company_is_buyer"]
    if seller is True or buyer is False:
        return [(if_seller, w)]
    if buyer is True or seller is False:
        return [(if_buyer, w)]
    if default:
        return [(default, w)]
    return [(if_seller, w / 2), (if_buyer, w / 2)]


def _not(v: bool | None) -> bool:
    return v is not True


@lf
def attendance(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Attendance", 3.0)] if c["attendance_fields"] and _not(c["has_money"]) else []


@lf
def payroll(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Salary / Payroll", 3.0)] if c["payroll_components"] else []


@lf
def physical_stock(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Physical Stock", 3.0)] if c["stock_count"] else []


@lf
def stock_journal(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Stock Journal", 3.0)] if c["godown_transfer"] else []


@lf
def job_work_order(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["job_work"] and c["order_without_movement"]:
        # The job worker supplies the processing service, so it sits on the seller side.
        return directional(c, "Job Work In Order", "Job Work Out Order", 3.0)
    return []


@lf
def job_work_material(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["job_work"] and _not(c["order_without_movement"]) and _not(c["has_invoice_values"]):
        return directional(c, "Material Out", "Material In", 2.5)
    return []


@lf
def order(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["order_without_movement"] and _not(c["job_work"]):
        return directional(c, "Sales Order", "Purchase Order", 2.5)
    return []


@lf
def rejection(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["kw_rejection"] and _not(c["has_invoice_values"]):
        return directional(c, "Rejection In", "Rejection Out", 2.5)
    return []


@lf
def receipt_note(c: EvidenceCard, p: Policy) -> list[Vote]:
    # A GRN is the receiver's document; in the sender's books it acknowledges a delivery.
    if c["has_grn"] and _not(c["has_invoice_values"]):
        return directional(c, "Delivery Note", "Receipt Note", 2.0, default="Receipt Note")
    return []


@lf
def delivery_note(c: EvidenceCard, p: Policy) -> list[Vote]:
    # A challan is the sender's document; in the receiver's books it is a receipt.
    if c["has_challan"] and _not(c["has_invoice_values"]) and _not(c["job_work"]):
        return directional(c, "Delivery Note", "Receipt Note", 2.0, default="Delivery Note")
    return []


@lf
def quantity_only(c: EvidenceCard, p: Policy) -> list[Vote]:
    known_side = c["company_is_seller"] is not None or c["company_is_buyer"] is not None
    if (
        c["quantity_without_value"]
        and known_side
        and _not(c["job_work"])
        and _not(c["kw_rejection"])
    ):
        return directional(c, "Delivery Note", "Receipt Note", 1.0)
    return []


@lf
def credit_note(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Sales Return / Credit Note", 2.0)] if c["kw_credit_note"] else []


@lf
def debit_note(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Purchase Return / Debit Note", 2.0)] if c["kw_debit_note"] else []


@lf
def return_by_sign(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["negative_value"] and c["references_other_document"]:
        return directional(c, "Sales Return / Credit Note", "Purchase Return / Debit Note", 2.0)
    return []


@lf
def cross_border_docs(c: EvidenceCard, p: Policy) -> list[Vote]:
    votes: list[Vote] = []
    if c["import_documents"]:
        votes.append(("Import", 3.0))
    if c["export_documents"]:
        votes.append(("Export", 3.0))
    if c["kw_sez"]:
        votes.append((p.sez_or_deemed_export, 2.0))
    return votes


@lf
def foreign_currency(c: EvidenceCard, p: Policy) -> list[Vote]:
    return directional(c, "Export", "Import", 1.5) if c["foreign_currency"] else []


@lf
def advance(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["kw_advance"] and c["has_money"] and _not(c["has_invoice_values"]):
        return [("Advance / Prepayment", 2.0)]
    return []


@lf
def contra(c: EvidenceCard, p: Policy) -> list[Vote]:
    return [("Contra", 3.0)] if c["both_legs_own_cash_bank"] else []


@lf
def settlement(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["both_legs_own_cash_bank"] or c["has_invoice_values"]:
        return []
    if c["credit_leg_own_cash_bank"]:
        return [("Payment", 2.0)]
    if c["debit_leg_own_cash_bank"]:
        return [("Receipt", 2.0)]
    return []


@lf
def supply_invoice(c: EvidenceCard, p: Policy) -> list[Vote]:
    if not (c["has_invoice_values"] or c["has_gst"]):
        return []
    inward = "Expense" if c["sac_service"] else "Purchase"
    if inward == "Expense" and c["payment_instrument"] and p.paid_expense_bill == "Payment":
        inward = "Payment"
    return directional(c, "Sales", inward, 2.0)


@lf
def journal(c: EvidenceCard, p: Policy) -> list[Vote]:
    if c["has_invoice_values"] or c["has_challan"] or c["has_grn"]:
        return []
    if c["kw_adjustment"]:
        return [("Journal", 2.0)]
    if c["debit_leg_own_cash_bank"] is False and c["credit_leg_own_cash_bank"] is False:
        return [("Journal", 1.5)]
    return []


_TIERS = len(PRECEDENCE)


def votes_to_distribution(votes: list[Vote]) -> np.ndarray:
    scores = np.full(len(LABELS), SMOOTHING)
    if not votes:
        scores[LABEL_INDEX[FALLBACK]] += 1.0
    for label, w in votes:
        # Precedence ladder as a soft tie-break: more specific tiers get a small bonus.
        scores[LABEL_INDEX[label]] += w * (1.0 + 0.05 * (_TIERS - 1 - RANK[label]))
    return scores / scores.sum()


class RulesOpinion:
    name = "rules"

    def __init__(self, policy: Policy):
        self.policy = policy

    def available(self) -> bool:
        return True

    def votes(self, card: EvidenceCard) -> list[Vote]:
        out: list[Vote] = []
        for _name, fn in LABELLING_FUNCTIONS:
            out.extend(fn(card, self.policy))
        return out

    def score(
        self,
        cards: Sequence[EvidenceCard],
        rows: Sequence[Mapping[str, object]],
        ctx: Context | None = None,
    ) -> np.ndarray:
        if not cards:
            return np.zeros((0, len(LABELS)))
        return np.vstack([votes_to_distribution(self.votes(c)) for c in cards])
