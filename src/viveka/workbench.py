"""Payload for the web workbench: predictions plus the context needed to show their working."""

from __future__ import annotations

from typing import Any

from viveka.labels import FAMILIES
from viveka.normalise import is_blank, norm_text
from viveka.pipeline import Run
from viveka.signals import EvidenceCard

AMOUNT_FIELDS = (
    "total_amount",
    "taxable_value",
    "debit_amount",
    "credit_amount",
    "net_pay",
    "gross_pay",
)


def _first(row: dict[str, object], *fields: str) -> object | None:
    return next((row[f] for f in fields if f in row and not is_blank(row[f])), None)


def counterparty(row: dict[str, object], card: EvidenceCard) -> str | None:
    """The other side of the entry, from the company's point of view."""
    if card["company_is_seller"] is True:
        return _first(row, "buyer_name", "party_name")
    if card["company_is_buyer"] is True:
        return _first(row, "seller_name", "party_name")
    if card["credit_leg_own_cash_bank"] is True and card["debit_leg_own_cash_bank"] is not True:
        return _first(row, "debit_account")
    if card["debit_leg_own_cash_bank"] is True and card["credit_leg_own_cash_bank"] is not True:
        return _first(row, "credit_account")
    return _first(
        row,
        "party_name",
        "employee_name",
        "employee_id",
        "job_worker",
        "seller_name",
        "buyer_name",
        "debit_account",
    )


def payload(result: Run, source_name: str) -> dict[str, Any]:
    headers = {m.field: m.header for m in result.mappings if m.field}
    rows = []
    for row, card in zip(result.rows, result.cards, strict=True):
        amount = _first(row, *AMOUNT_FIELDS)
        rows.append(
            {
                "row_id": card.row_id,
                "date": _first(row, "invoice_date", "order_date"),
                "number": _first(row, "invoice_number", "order_number", "challan_number"),
                "party": counterparty(row, card),
                "amount": amount if isinstance(amount, int | float) else None,
                "currency": norm_text(row.get("currency")).upper() or None,
                "quantity": _first(row, "quantity", "physical_quantity"),
                "unit": _first(row, "unit"),
                "item": _first(row, "item_name"),
                "narration": _first(row, "narration"),
                "fields": [
                    {"field": k, "header": headers.get(k, k.removeprefix("extra:")), "value": v}
                    for k, v in row.items()
                    if not k.startswith("_") and not is_blank(v)
                ],
            }
        )
    ctx = result.context
    # The context keeps names normalised; show the spelling used in the file.
    name = next(
        (
            str(r[f])
            for r in result.rows
            for f in ("seller_name", "buyer_name")
            if ctx.company_name and norm_text(r.get(f)) == ctx.company_name
        ),
        ctx.company_name,
    )
    return {
        "source": source_name,
        "company": {
            "gstin": ctx.company_gstin,
            "name": name,
            "how": ctx.source,
            "own_accounts": sorted(ctx.own_accounts),
        },
        "mappings": [
            {"header": m.header, "field": m.field, "stage": m.stage, "score": m.score}
            for m in result.mappings
        ],
        "families": [{"name": name, "labels": list(labels)} for name, labels in FAMILIES],
        "rows": rows,
        "predictions": [p.model_dump(mode="json") for p in result.predictions],
    }
