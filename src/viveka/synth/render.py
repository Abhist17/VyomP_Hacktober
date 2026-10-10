"""Turn canonical event rows into messy spreadsheets: header dialects, formats and noise.

Writes one workbook per company (whose books) plus a gold CSV in the same row order.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook

from viveka.schema import AMOUNT, CANONICAL, FIELD_KIND, SYNONYM_TO_FIELD, normalise_header
from viveka.synth.world import Company


@dataclass(frozen=True)
class Dialect:
    """How one source system exports its books."""

    name: str
    date_fmt: str | None  # None writes native Excel dates
    amounts: str  # plain | indian | parens
    drop: float  # chance that a non-core field is left blank
    title_rows: bool  # report title above the header row
    doc_type: bool  # adds a coarse document-type column


SEEN_DIALECTS = (
    Dialect("tally_daybook", "%d-%m-%Y", "indian", 0.08, True, False),
    Dialect("erp_export", None, "plain", 0.12, False, True),
    Dialect("ca_worksheet", "%d/%m/%Y", "parens", 0.10, False, False),
    Dialect("api_dump", "%Y-%m-%d", "plain", 0.15, False, False),
)
UNSEEN_DIALECT = Dialect("legacy_sheet", "%d.%m.%Y", "indian", 0.18, True, False)

# Narrations that use another voucher type's vocabulary without changing what happened.
TRAPS = (
    "As discussed, refer return mail dated 12th",
    "Journal ref 44 checked by accounts",
    "Order ref: verbal confirmation",
    "Advance copy sent by email",
    "Contra check pending with bank",
    "Credit period 30 days",
    "Debit as per party statement",
    "Payment terms 45 days",
    "Received via courier",
    "Export quality packing",
    "Import file updated",
    "Approved by salary section head",
    "Stock to be verified later",
    "Transfer to be confirmed",
)

# Coarse document types an ERP export might carry (never the voucher type itself).
_DOC_TYPE = {
    "Purchase": "Tax Invoice",
    "Sales": "Tax Invoice",
    "Expense": "Tax Invoice",
    "Import": "Invoice",
    "Export": "Tax Invoice",
    "Payment": "Bank/Cash Voucher",
    "Receipt": "Bank/Cash Voucher",
    "Contra": "Bank/Cash Voucher",
    "Advance / Prepayment": "Bank/Cash Voucher",
    "Journal": "Voucher",
    "Other / Miscellaneous": "Voucher",
    "Receipt Note": "Challan",
    "Delivery Note": "Challan",
    "Rejection In": "Challan",
    "Rejection Out": "Challan",
    "Material In": "Challan",
    "Material Out": "Challan",
    "Stock Journal": "Stock Entry",
    "Physical Stock": "Stock Entry",
    "Purchase Order": "Order",
    "Sales Order": "Order",
    "Job Work In Order": "Order",
    "Job Work Out Order": "Order",
    "Salary / Payroll": "HR Register",
    "Attendance": "HR Register",
}

_FIELD_ORDER = {name: i for i, name in enumerate(CANONICAL)}


def headers_for(dialect: Dialect) -> dict[str, str]:
    """One header per canonical field, drawn from synonyms the aligner maps back exactly."""
    rng = random.Random(f"headers:{dialect.name}")
    out = {}
    for field, (_kind, synonyms) in CANONICAL.items():
        if dialect.name == "api_dump":
            out[field] = field
            continue
        exact = [s for s in synonyms if SYNONYM_TO_FIELD.get(normalise_header(s)) == field]
        # Very short synonyms ("to", "dr", "pos") are legal but rare in exports; prefer longer.
        longer = [s for s in exact if len(s) > 3] or exact or [field]
        header = rng.choice(longer)
        out[field] = header.title() if dialect.amounts != "plain" else header
    return out


def _indian(value: float) -> str:
    whole, frac = f"{abs(value):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join([*groups, tail]) + "." + frac
    return f"-{text}" if value < 0 else text


def _format(field: str, value: object, dialect: Dialect) -> object:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value if dialect.date_fmt is None else value.strftime(dialect.date_fmt)
    if FIELD_KIND.get(field) == AMOUNT and isinstance(value, int | float):
        if dialect.amounts == "plain":
            return float(value)
        text = _indian(float(value))
        if dialect.amounts == "parens" and text.startswith("-"):
            return f"({text[1:]})"
        return text
    return value


def _name_variant(name: str, rng: random.Random) -> str:
    choice = rng.randrange(3)
    if choice == 0:
        return name.upper()
    if choice == 1:
        return name.replace("Pvt Ltd", "Pvt. Ltd.").replace("Private Limited", "Pvt Ltd")
    return " ".join(name.split()[:2])


def add_noise(
    row: dict[str, object],
    label: str,
    core: tuple[str, ...],
    company: Company,
    dialect: Dialect,
    rng: random.Random,
) -> dict[str, object]:
    """Blanks, misleading narrations and inconsistent spellings of the company's name."""
    out = dict(row)
    for field in list(out):
        if field == "invoice_number" or out[field] is None:
            continue
        p = dialect.drop / 3 if field in core else dialect.drop
        if rng.random() < p:
            out[field] = None
    r = rng.random()
    if r < 0.10:
        out["narration"] = rng.choice(TRAPS)
    elif out.get("narration") and r < 0.30:
        out["narration"] = None
    for field in ("seller_name", "buyer_name"):
        if out.get(field) == company.name and rng.random() < 0.10:
            out[field] = _name_variant(company.name, rng)
    if dialect.doc_type and not out.get("document_type"):
        out["document_type"] = _DOC_TYPE.get(label)
    return out


def write_book(
    path: Path,
    rows: list[dict[str, object]],
    company: Company,
    dialect: Dialect,
    title: str,
) -> None:
    headers = headers_for(dialect)
    fields = sorted(
        {f for r in rows for f, v in r.items() if v is not None and v != ""},
        key=lambda f: (f.startswith("extra:"), _FIELD_ORDER.get(f, 999), f),
    )
    names = [f.removeprefix("extra:") if f.startswith("extra:") else headers[f] for f in fields]
    wb = Workbook()
    ws = wb.active
    ws.title = "Day Book"
    if dialect.title_rows:
        ws.append([company.name])
        ws.append([title])
        ws.append([])
    ws.append(names)
    for r in rows:
        ws.append([_format(f, None if r.get(f) == "" else r.get(f), dialect) for f in fields])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


GOLD_FIELDS = ("Invoice No", "Voucher Type", "Template", "Heldout", "Company")


def write_gold(path: Path, gold: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(GOLD_FIELDS))
        writer.writeheader()
        writer.writerows(gold)
