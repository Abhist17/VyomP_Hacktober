"""Signal extractors and the evidence card.

Each signal is three-valued (True / False / None for unknown) and records the
canonical fields it came from. Add signals with the `@signal` decorator.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from viveka.context import Context
from viveka.normalise import code_kind, is_blank, norm_text, parse_amount

Row = Mapping[str, object]
Tri = bool | None


@dataclass(frozen=True)
class Signal:
    name: str
    value: Tri
    fields: tuple[str, ...] = ()


@dataclass
class EvidenceCard:
    row_id: int
    signals: dict[str, Signal] = field(default_factory=dict)

    def __getitem__(self, name: str) -> Tri:
        s = self.signals.get(name)
        return None if s is None else s.value

    def true(self) -> list[Signal]:
        return [s for s in self.signals.values() if s.value is True]

    def render(self) -> str:
        lines = [f"EVIDENCE CARD · row {self.row_id}"]
        for s in self.signals.values():
            if s.value is None:
                continue
            src = f"  [{', '.join(s.fields)}]" if s.fields else ""
            lines.append(f"{s.name:<28}: {str(s.value).upper()}{src}")
        return "\n".join(lines)


_REGISTRY: list[tuple[str, str, Callable[[Row, Context], Signal]]] = []


def signal(name: str, family: str):
    def register(fn: Callable[[Row, Context], tuple[Tri, tuple[str, ...]]]):
        def wrapped(row: Row, ctx: Context) -> Signal:
            value, fields = fn(row, ctx)
            return Signal(name, value, fields)

        _REGISTRY.append((name, family, wrapped))
        return fn

    return register


def registered() -> list[tuple[str, str]]:
    return [(name, family) for name, family, _ in _REGISTRY]


# --- helpers -------------------------------------------------------------------------------


def _present(row: Row, *fields: str) -> tuple[str, ...]:
    return tuple(f for f in fields if f in row and not is_blank(row.get(f)))


def _nonzero(row: Row, *fields: str) -> tuple[str, ...]:
    return tuple(f for f in fields if (parse_amount(row.get(f)) or 0) != 0)


def _any_known(row: Row, *fields: str) -> bool:
    return any(f in row for f in fields)


def _text(row: Row) -> str:
    """All free text on the row: narration, document type, item name and unmapped columns."""
    parts = [row.get(f) for f in ("narration", "document_type", "item_name", "reason")]
    parts += [v for k, v in row.items() if str(k).startswith("extra:") and isinstance(v, str)]
    return " ".join(norm_text(p) for p in parts if not is_blank(p))


def _kw(row: Row, pattern: str) -> tuple[Tri, tuple[str, ...]]:
    text = _text(row)
    if not text:
        return None, ()
    return bool(re.search(pattern, text)), ("narration",)


MONEY = (
    "taxable_value",
    "total_amount",
    "debit_amount",
    "credit_amount",
    "rate",
    "net_pay",
    "gross_pay",
)
INVOICE_VALUES = ("taxable_value", "cgst", "sgst", "igst", "cess")
GST = ("cgst", "sgst", "igst", "cess")
PAYROLL = ("basic_pay", "hra", "pf", "esi", "gross_pay", "net_pay")
ATTENDANCE = ("days_present", "days_absent", "overtime_hours")

# --- perspective ---------------------------------------------------------------------------


@signal("company_is_seller", "perspective")
def _company_is_seller(row: Row, ctx: Context):
    return ctx.is_company(row.get("seller_gstin"), row.get("seller_name")), _present(
        row, "seller_gstin", "seller_name"
    )


@signal("company_is_buyer", "perspective")
def _company_is_buyer(row: Row, ctx: Context):
    return ctx.is_company(row.get("buyer_gstin"), row.get("buyer_name")), _present(
        row, "buyer_gstin", "buyer_name"
    )


# --- money legs ----------------------------------------------------------------------------


@signal("has_money", "money")
def _has_money(row: Row, ctx: Context):
    if not _any_known(row, *MONEY):
        return None, ()
    hits = _nonzero(row, *MONEY)
    return bool(hits), hits


@signal("debit_leg_own_cash_bank", "money")
def _debit_own(row: Row, ctx: Context):
    return ctx.is_own_account(row.get("debit_account")), _present(row, "debit_account")


@signal("credit_leg_own_cash_bank", "money")
def _credit_own(row: Row, ctx: Context):
    return ctx.is_own_account(row.get("credit_account")), _present(row, "credit_account")


@signal("both_legs_own_cash_bank", "money")
def _both_own(row: Row, ctx: Context):
    d, c = (
        ctx.is_own_account(row.get("debit_account")),
        ctx.is_own_account(row.get("credit_account")),
    )
    fields = _present(row, "debit_account", "credit_account")
    if d is False or c is False:
        return False, fields
    if d is None or c is None:
        return None, fields
    return True, fields


@signal("payment_instrument", "money")
def _instrument(row: Row, ctx: Context):
    hits = _present(row, "payment_mode", "payment_reference")
    if hits:
        return True, hits
    return _kw(row, r"\b(neft|rtgs|imps|upi|cheque|chq|dd)\b")


# --- document nature -----------------------------------------------------------------------


@signal("has_invoice_values", "document")
def _invoice_values(row: Row, ctx: Context):
    if not _any_known(row, *INVOICE_VALUES):
        return None, ()
    hits = _nonzero(row, *INVOICE_VALUES)
    return bool(hits), hits


@signal("references_other_document", "document")
def _references(row: Row, ctx: Context):
    if not _any_known(row, "reference_number"):
        return None, ()
    hits = _present(row, "reference_number")
    return bool(hits), hits


@signal("negative_value", "document")
def _negative(row: Row, ctx: Context):
    vals = [(f, parse_amount(row.get(f))) for f in ("taxable_value", "total_amount", "quantity")]
    vals = [(f, v) for f, v in vals if v is not None]
    if not vals:
        return None, ()
    neg = tuple(f for f, v in vals if v < 0)
    return bool(neg), neg


@signal("order_without_movement", "document")
def _order_only(row: Row, ctx: Context):
    order = _present(row, "order_number", "order_date", "due_date")
    if not order:
        return (False, ()) if _any_known(row, "order_number") else (None, ())
    moved = _present(row, "challan_number", "grn_number") or _nonzero(row, *GST)
    return not moved, order


@signal("kw_credit_note", "document")
def _kw_cn(row: Row, ctx: Context):
    return _kw(row, r"\b(credit note|cn|sales return|sales ret|sale return)\b")


@signal("kw_debit_note", "document")
def _kw_dn(row: Row, ctx: Context):
    return _kw(row, r"\b(debit note|dn|purchase return|pur ret|purchase ret)\b")


@signal("kw_advance", "document")
def _kw_adv(row: Row, ctx: Context):
    return _kw(row, r"\b(advance|adv|on account|token|prepaid|against po|against so|agst po)\b")


@signal("kw_adjustment", "document")
def _kw_adj(row: Row, ctx: Context):
    return _kw(
        row,
        r"\b(depreciation|provision|accrual|write ?off|rectification|jv|journal|"
        r"set ?off|tds payable)\b",
    )


# --- GST and goods vs services -------------------------------------------------------------


@signal("has_gst", "gst")
def _has_gst(row: Row, ctx: Context):
    if not _any_known(row, *GST):
        return None, ()
    hits = _nonzero(row, *GST)
    return bool(hits), hits


@signal("sac_service", "gst")
def _sac(row: Row, ctx: Context):
    kind = code_kind(row.get("hsn_sac"))
    return (None, ()) if kind is None else (kind == "SAC", ("hsn_sac",))


# --- inventory -----------------------------------------------------------------------------


@signal("quantity_without_value", "inventory")
def _qty_no_value(row: Row, ctx: Context):
    if not _present(row, "quantity"):
        return (False, ()) if _any_known(row, "quantity") else (None, ())
    return not _nonzero(row, "taxable_value", "rate", "total_amount"), ("quantity",)


@signal("has_challan", "inventory")
def _challan(row: Row, ctx: Context):
    fields = ("challan_number", "eway_bill", "vehicle_number")
    if not _any_known(row, *fields):
        return None, ()
    hits = _present(row, *fields)
    return bool(hits), hits


@signal("has_grn", "inventory")
def _grn(row: Row, ctx: Context):
    if not _any_known(row, "grn_number"):
        return None, ()
    hits = _present(row, "grn_number")
    return bool(hits), hits


@signal("kw_rejection", "inventory")
def _kw_rej(row: Row, ctx: Context):
    return _kw(row, r"\b(reject|rejected|rejection|qc fail|quality fail)\b")


@signal("godown_transfer", "inventory")
def _godown(row: Row, ctx: Context):
    if not _any_known(row, "destination_godown"):
        return None, ()
    hits = _present(row, "godown", "destination_godown")
    return len(hits) == 2, hits


@signal("stock_count", "inventory")
def _count(row: Row, ctx: Context):
    if not _any_known(row, "physical_quantity"):
        return None, ()
    hits = _present(row, "physical_quantity", "book_quantity")
    return "physical_quantity" in hits, hits


# --- job work ------------------------------------------------------------------------------


@signal("job_work", "job_work")
def _job_work(row: Row, ctx: Context):
    hits = _present(row, "job_worker", "process")
    if hits:
        return True, hits
    return _kw(row, r"\b(job ?work|jobwork|job worker|itc-?04|principal)\b")


# --- payroll -------------------------------------------------------------------------------


@signal("payroll_components", "payroll")
def _payroll(row: Row, ctx: Context):
    if not _any_known(row, *PAYROLL):
        return None, ()
    hits = _nonzero(row, *PAYROLL)
    return bool(hits), hits


@signal("attendance_fields", "payroll")
def _attendance(row: Row, ctx: Context):
    if not _any_known(row, *ATTENDANCE):
        return None, ()
    hits = _present(row, *ATTENDANCE)
    return bool(hits), hits


@signal("employee_present", "payroll")
def _employee(row: Row, ctx: Context):
    if not _any_known(row, "employee_id", "employee_name"):
        return None, ()
    hits = _present(row, "employee_id", "employee_name")
    return bool(hits), hits


# --- cross-border --------------------------------------------------------------------------


@signal("import_documents", "cross_border")
def _import_docs(row: Row, ctx: Context):
    hits = _present(row, "bill_of_entry", "customs_duty")
    if hits:
        return True, hits
    return (False, ()) if _any_known(row, "bill_of_entry", "customs_duty") else (None, ())


@signal("export_documents", "cross_border")
def _export_docs(row: Row, ctx: Context):
    hits = _present(row, "shipping_bill", "lut")
    if hits:
        return True, hits
    return _kw(row, r"\b(supply meant for export|expwp|expwop|lut|shipping bill|fob|cif)\b")


@signal("foreign_currency", "cross_border")
def _foreign(row: Row, ctx: Context):
    cur = norm_text(row.get("currency"))
    if not cur:
        return None, ()
    return cur not in {"inr", "rs", "rs.", "₹", "rupees"}, ("currency",)


@signal("kw_sez", "cross_border")
def _kw_sez(row: Row, ctx: Context):
    return _kw(row, r"\b(sez|special economic zone|deemed export)\b")


def build_card(row: Row, ctx: Context) -> EvidenceCard:
    card = EvidenceCard(row_id=int(row.get("_row_id", 0)))
    for name, _family, fn in _REGISTRY:
        card.signals[name] = fn(row, ctx)
    return card
