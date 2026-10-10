"""The 27 voucher labels, spelled exactly as in the problem statement."""

from __future__ import annotations

LABELS: tuple[str, ...] = (
    "Purchase",
    "Sales",
    "Purchase Return / Debit Note",
    "Sales Return / Credit Note",
    "Payment",
    "Receipt",
    "Contra",
    "Journal",
    "Salary / Payroll",
    "Attendance",
    "Purchase Order",
    "Sales Order",
    "Receipt Note",
    "Delivery Note",
    "Rejection In",
    "Rejection Out",
    "Stock Journal",
    "Physical Stock",
    "Material In",
    "Material Out",
    "Job Work In Order",
    "Job Work Out Order",
    "Import",
    "Export",
    "Expense",
    "Advance / Prepayment",
    "Other / Miscellaneous",
)

LABEL_INDEX: dict[str, int] = {label: i for i, label in enumerate(LABELS)}

FALLBACK = "Other / Miscellaneous"

# Labels that flip when the owner of the books changes (perspective-swap test).
_DIRECTIONAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("Purchase", "Sales"),
    ("Purchase Return / Debit Note", "Sales Return / Credit Note"),
    ("Payment", "Receipt"),
    ("Import", "Export"),
    ("Rejection Out", "Rejection In"),
    ("Purchase Order", "Sales Order"),
    ("Receipt Note", "Delivery Note"),
    ("Material In", "Material Out"),
    ("Job Work Out Order", "Job Work In Order"),
)

FLIP: dict[str, str] = {}
for _a, _b in _DIRECTIONAL_PAIRS:
    FLIP[_a] = _b
    FLIP[_b] = _a


def flip(label: str) -> str:
    """Return the label as seen from the counterparty's books."""
    return FLIP.get(label, label)


# Playbook families (README section 2.2), used to group labels in interfaces.
FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Money movements", ("Payment", "Receipt", "Contra", "Journal")),
    ("Supply invoices", ("Sales", "Purchase", "Expense", "Import", "Export")),
    ("Value corrections", ("Sales Return / Credit Note", "Purchase Return / Debit Note")),
    (
        "Orders",
        ("Purchase Order", "Sales Order", "Job Work Out Order", "Job Work In Order"),
    ),
    (
        "Inventory movements",
        (
            "Receipt Note",
            "Delivery Note",
            "Rejection In",
            "Rejection Out",
            "Material In",
            "Material Out",
            "Stock Journal",
            "Physical Stock",
        ),
    ),
    ("People", ("Salary / Payroll", "Attendance")),
    ("Timing and fallback", ("Advance / Prepayment", "Other / Miscellaneous")),
)


# Default precedence ladder (README section 2.2): most specific reading wins.
PRECEDENCE: tuple[tuple[str, ...], ...] = (
    ("Attendance", "Salary / Payroll"),
    ("Purchase Order", "Sales Order", "Job Work Out Order", "Job Work In Order"),
    ("Material Out", "Material In"),
    (
        "Rejection In",
        "Rejection Out",
        "Receipt Note",
        "Delivery Note",
        "Stock Journal",
        "Physical Stock",
    ),
    ("Sales Return / Credit Note", "Purchase Return / Debit Note"),
    ("Import", "Export"),
    ("Advance / Prepayment",),
    ("Contra",),
    ("Payment", "Receipt"),
    ("Sales", "Purchase", "Expense"),
    ("Journal",),
    ("Other / Miscellaneous",),
)

RANK: dict[str, int] = {label: tier for tier, group in enumerate(PRECEDENCE) for label in group}

# The seven confusable pairs named in the problem statement, for the pair scoreboard.
CONFUSABLE_PAIRS: dict[str, frozenset[str]] = {
    "Purchase vs Sales": frozenset({"Purchase", "Sales"}),
    "Purchase Return vs Sales Return": frozenset(
        {"Purchase Return / Debit Note", "Sales Return / Credit Note"}
    ),
    "Salary / Payroll vs others": frozenset({"Salary / Payroll", "Attendance", "Payment"}),
    "Contra vs Payment / Receipt": frozenset({"Contra", "Payment", "Receipt"}),
    "Journal vs Purchase / Sales": frozenset({"Journal", "Purchase", "Sales"}),
    "Inventory movement vs Purchase / Sales": frozenset(
        {
            "Receipt Note",
            "Delivery Note",
            "Rejection In",
            "Rejection Out",
            "Stock Journal",
            "Physical Stock",
            "Material In",
            "Material Out",
            "Purchase",
            "Sales",
        }
    ),
    "Import / Export vs others": frozenset({"Import", "Export", "Purchase", "Sales"}),
}

assert len(LABELS) == 27 and len(set(LABELS)) == 27
assert set(RANK) == set(LABELS)
assert sorted(label for _, group in FAMILIES for label in group) == sorted(LABELS)
