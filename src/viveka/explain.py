"""Template explanations built from the evidence card, faithful by construction.

TODO(block 6): one-question clarifier that best splits the prediction set.
"""

from __future__ import annotations

from viveka.signals import EvidenceCard

# Signals worth citing for each label; the true ones are quoted in the explanation.
LABEL_SIGNALS: dict[str, tuple[str, ...]] = {
    "Purchase": ("company_is_buyer", "has_invoice_values", "has_gst"),
    "Sales": ("company_is_seller", "has_invoice_values", "has_gst"),
    "Purchase Return / Debit Note": (
        "kw_debit_note",
        "negative_value",
        "references_other_document",
    ),
    "Sales Return / Credit Note": ("kw_credit_note", "negative_value", "references_other_document"),
    "Payment": ("credit_leg_own_cash_bank", "payment_instrument"),
    "Receipt": ("debit_leg_own_cash_bank", "payment_instrument"),
    "Contra": ("both_legs_own_cash_bank",),
    "Journal": ("kw_adjustment",),
    "Salary / Payroll": ("payroll_components", "employee_present"),
    "Attendance": ("attendance_fields", "employee_present"),
    "Purchase Order": ("order_without_movement", "company_is_buyer"),
    "Sales Order": ("order_without_movement", "company_is_seller"),
    "Receipt Note": ("has_grn", "quantity_without_value"),
    "Delivery Note": ("has_challan", "quantity_without_value"),
    "Rejection In": ("kw_rejection", "company_is_seller"),
    "Rejection Out": ("kw_rejection", "company_is_buyer"),
    "Stock Journal": ("godown_transfer",),
    "Physical Stock": ("stock_count",),
    "Material In": ("job_work", "has_challan"),
    "Material Out": ("job_work", "has_challan"),
    "Job Work In Order": ("job_work", "order_without_movement"),
    "Job Work Out Order": ("job_work", "order_without_movement"),
    "Import": ("import_documents", "foreign_currency"),
    "Export": ("export_documents", "foreign_currency", "kw_sez"),
    "Expense": ("sac_service", "has_invoice_values"),
    "Advance / Prepayment": ("kw_advance",),
    "Other / Miscellaneous": (),
}


def explain(
    label: str,
    card: EvidenceCard,
    alternatives: list[tuple[str, float]],
    guardrail_notes: list[str],
) -> str:
    cited = [
        card.signals[name]
        for name in LABEL_SIGNALS.get(label, ())
        if name in card.signals and card.signals[name].value is True
    ]
    if cited:
        because = "; ".join(
            s.name.replace("_", " ") + (f" ({', '.join(s.fields)})" if s.fields else "")
            for s in cited
        )
        text = f"{label} because: {because}."
    else:
        text = f"{label}: no decisive evidence for any category; best available reading."
    if alternatives:
        alt = ", ".join(f"{lbl} ({p:.0%})" for lbl, p in alternatives)
        text += f" Also possible: {alt}."
    if guardrail_notes:
        text += " " + " ".join(guardrail_notes) + "."
    return text
