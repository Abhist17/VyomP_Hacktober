"""Accounting events, one template per way a voucher type shows up in a company's books.

Each template returns one row of canonical fields, built from what happened (who supplied
whom, which ledgers moved, whether goods or only documents moved). Templates never look at
`viveka.signals` or `viveka.models.rules`, so the rules are not scored against themselves.

Directional pairs share an event shape and differ only in which side the company is on.
Templates marked `heldout` appear only in the unseen test split.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from viveka.labels import LABELS
from viveka.synth.world import JOB_PROCESSES, SERVICES, Company, Party

Row = dict[str, object]
Fn = Callable[[Company, random.Random, date], Row]


@dataclass(frozen=True)
class Template:
    label: str
    name: str
    fn: Fn
    heldout: bool
    core: tuple[str, ...]


TEMPLATES: dict[str, list[Template]] = {label: [] for label in LABELS}


def template(label: str, *, heldout: bool = False, core: tuple[str, ...] = ()):
    def register(fn: Fn) -> Fn:
        TEMPLATES[label].append(Template(label, fn.__name__, fn, heldout, core))
        return fn

    return register


# --- helpers -------------------------------------------------------------------------------

_QTY = {"MT": (1.0, 25.0), "KG": (50, 5000), "NOS": (5, 600), "MTR": (100, 5000)}


def _qty(rng: random.Random, unit: str) -> float:
    lo, hi = _QTY[unit]
    return round(rng.uniform(lo, hi), 2) if unit == "MT" else float(rng.randint(lo, hi))


def _goods(c: Company, rng: random.Random, valued: bool = True) -> Row:
    name, hsn, unit, (lo, hi) = rng.choice(c.goods)
    row: Row = {"item_name": name, "hsn_sac": hsn, "quantity": _qty(rng, unit), "unit": unit}
    if valued:
        rate = round(rng.uniform(lo, hi), 2)
        row |= {"rate": rate, "taxable_value": round(row["quantity"] * rate, 2)}
    return row


def _tax(rng: random.Random, taxable: float, intra: bool, rate: int | None = None) -> Row:
    rate = rate if rate is not None else rng.choice((5, 12, 18, 18, 18, 28))
    tax = round(taxable * rate / 100, 2)
    if intra:
        half = round(tax / 2, 2)
        return {"gst_rate": rate, "cgst": half, "sgst": half, "total_amount": taxable + 2 * half}
    return {"gst_rate": rate, "igst": tax, "total_amount": round(taxable + tax, 2)}


def _sides(seller: Company | Party, buyer: Company | Party) -> Row:
    return {
        "seller_name": seller.name,
        "seller_gstin": seller.gstin,
        "buyer_name": buyer.name,
        "buyer_gstin": buyer.gstin,
    }


def _their_number(p: Party, rng: random.Random) -> str:
    style = rng.randrange(3)
    if style == 0:
        return f"{p.prefix}/{rng.randint(100, 9999)}"
    if style == 1:
        return f"INV-2026-{rng.randint(1000, 9999)}"
    return f"{p.prefix}{rng.randint(10, 99)}/26-27/{rng.randint(1, 999):03d}"


def _bank(c: Company, rng: random.Random) -> str:
    return rng.choice(c.banks)


def _utr(rng: random.Random, mode: str) -> str:
    if mode == "Cheque":
        return f"{rng.randint(100000, 999999)}"
    if mode == "UPI":
        return f"{rng.randint(10**11, 10**12 - 1)}"
    return f"{rng.choice(('HDFC', 'SBIN', 'ICIC', 'UTIB'))}R{rng.randint(10**10, 10**11 - 1)}"


def _amount(rng: random.Random, lo: int, hi: int) -> float:
    return float(round(rng.uniform(lo, hi), -1))


def _pick(rng: random.Random, *options: str) -> str:
    return rng.choice(options)


def _intra(c: Company, p: Party) -> bool:
    return c.state == p.state


def _vehicle(rng: random.Random) -> str:
    state = rng.choice(("MH", "GJ", "KA", "TN", "DL", "UP"))
    series = rng.choice("ABCDEFGHJK") + rng.choice("ABCDEFGHJK")
    return f"{state}{rng.randint(1, 48):02d}{series}{rng.randint(1000, 9999)}"


def _period(d: date) -> str:
    return f"{(d.replace(day=1) - timedelta(days=1)):%b-%Y}"


# --- supply invoices -----------------------------------------------------------------------


@template("Purchase", core=("seller_name", "buyer_name", "taxable_value"))
def purchase_goods(c, rng, d):
    p = c.party("supplier", rng)
    row = _sides(p, c) | _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], _intra(c, p))
    item = row["item_name"]
    return row | {
        "invoice_number": _their_number(p, rng),
        "invoice_date": d,
        "narration": _pick(
            rng,
            f"Purchase of {item}",
            "Tax invoice",
            f"Bill for {item}",
            "Material purchased",
            "As per bill",
            "",
        ),
    }


@template("Purchase", core=("seller_name", "buyer_name", "taxable_value"))
def purchase_with_po_grn(c, rng, d):
    p = c.party("supplier", rng)
    row = _sides(p, c) | _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], _intra(c, p))
    freight = _amount(rng, 500, 8000)
    row["freight"] = freight
    row["total_amount"] = round(row["total_amount"] + freight, 2)
    return row | {
        "invoice_number": _their_number(p, rng),
        "invoice_date": d,
        "order_number": f"{c.prefix}/PO/{rng.randint(100, 999)}",
        "grn_number": f"GRN-{rng.randint(1000, 9999)}",
        "narration": _pick(
            rng,
            "Against PO and GRN",
            "Bill received for material inward",
            "Purchase bill incl. freight",
            "",
        ),
    }


@template("Purchase", heldout=True, core=("seller_name", "buyer_name", "taxable_value"))
def purchase_unregistered_rcm(c, rng, d):
    name = f"{rng.choice(('Ganesh', 'Laxmi', 'Sai', 'Hari'))} Scrap Dealers"
    row: Row = {"seller_name": name, "buyer_name": c.name, "buyer_gstin": c.gstin}
    row |= _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], True, 18)
    return row | {
        "invoice_number": f"KB-{rng.randint(10, 999)}",
        "invoice_date": d,
        "reverse_charge": "Yes",
        "narration": _pick(
            rng, "Purchased from unregistered dealer, RCM applicable", "Kachcha bill", ""
        ),
    }


@template("Sales", core=("seller_name", "buyer_name", "taxable_value"))
def sales_b2b(c, rng, d):
    p = c.party("customer", rng)
    row = _sides(c, p) | _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], _intra(c, p))
    return row | {
        "invoice_number": c.next_number("S", rng),
        "invoice_date": d,
        "narration": _pick(
            rng,
            "Tax invoice",
            f"Sale of {row['item_name']}",
            "Being goods sold",
            "Supply as per order",
            "",
        ),
    }


@template("Sales", core=("seller_name", "buyer_name", "taxable_value"))
def sales_with_dispatch(c, rng, d):
    p = c.party("customer", rng)
    row = _sides(c, p) | _goods(c, rng)
    disc = round(row["taxable_value"] * rng.choice((0.02, 0.03, 0.05)), 2)
    row["discount"] = disc
    row["taxable_value"] = round(row["taxable_value"] - disc, 2)
    row |= _tax(rng, row["taxable_value"], _intra(c, p))
    return row | {
        "invoice_number": c.next_number("S", rng),
        "invoice_date": d,
        "eway_bill": f"{rng.randint(10**11, 10**12 - 1)}",
        "vehicle_number": _vehicle(rng),
        "order_number": f"{p.prefix}/PO/{rng.randint(100, 999)}",
        "narration": _pick(
            rng,
            "Invoice with e-way bill",
            "Goods dispatched against your PO",
            "Cash discount allowed",
            "",
        ),
    }


@template("Sales", heldout=True, core=("seller_name", "taxable_value"))
def sales_b2c_counter(c, rng, d):
    row: Row = {
        "seller_name": c.name,
        "seller_gstin": c.gstin,
        "buyer_name": _pick(rng, "Walk-in Customer", "Cash Sale", "Retail Customer"),
    }
    row |= _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], True)
    return row | {
        "invoice_number": c.next_number("B2C", rng),
        "invoice_date": d,
        "payment_mode": _pick(rng, "Cash", "UPI"),
        "payment_status": "Paid",
        "narration": _pick(rng, "Counter sale", "B2C invoice, paid at counter", ""),
    }


@template("Expense", core=("seller_name", "item_name", "taxable_value"))
def expense_service_bill(c, rng, d):
    p = c.party("vendor", rng)
    desc, sac, (lo, hi) = rng.choice(SERVICES)
    taxable = _amount(rng, lo, hi)
    row = _sides(p, c) | {"item_name": desc, "hsn_sac": sac, "taxable_value": taxable}
    row |= _tax(rng, taxable, _intra(c, p), 18)
    return row | {
        "invoice_number": _their_number(p, rng),
        "invoice_date": d,
        "narration": _pick(rng, f"{desc} for {d:%b %Y}", "Service bill", desc, ""),
    }


@template("Expense", core=("seller_name", "taxable_value"))
def expense_paid_utility(c, rng, d):
    vendor, code, rate = rng.choice(
        (
            ("State Electricity Distribution Co Ltd", "27160000", 0),
            ("Bharti Airtel Ltd", "998413", 18),
            ("City Gas Distribution Ltd", "27112100", 5),
        )
    )
    taxable = _amount(rng, 2000, 90000)
    row: Row = {
        "seller_name": vendor,
        "buyer_name": c.name,
        "buyer_gstin": c.gstin,
        "item_name": _pick(rng, "Utility bill", "Monthly bill"),
        "hsn_sac": code,
        "taxable_value": taxable,
    }
    row |= _tax(rng, taxable, True, rate)
    mode = _pick(rng, "UPI", "NEFT", "Auto debit")
    return row | {
        "invoice_number": f"{rng.randint(10**8, 10**9 - 1)}",
        "invoice_date": d,
        "payment_mode": mode,
        "payment_reference": _utr(rng, "UPI" if mode == "UPI" else "NEFT"),
        "payment_status": "Paid",
        "narration": _pick(rng, f"Bill for {d:%B} paid online", "Paid on due date", ""),
    }


@template("Expense", core=("seller_name", "item_name"))
def expense_office_supplies(c, rng, d):
    p = c.party("vendor", rng)
    item, hsn = rng.choice(
        (
            ("Office stationery", "4820"),
            ("Printer cartridges", "8443"),
            ("Pantry supplies", "2101"),
            ("Cleaning material", "3402"),
        )
    )
    taxable = _amount(rng, 800, 15000)
    row = _sides(p, c) | {"item_name": item, "hsn_sac": hsn, "taxable_value": taxable}
    row |= _tax(rng, taxable, _intra(c, p))
    return row | {
        "invoice_number": _their_number(p, rng),
        "invoice_date": d,
        "narration": _pick(
            rng, "For office use", "Consumed in office, not for resale", "Office expenses", ""
        ),
    }


@template("Expense", heldout=True, core=("seller_name", "taxable_value"))
def expense_gta_rcm(c, rng, d):
    name = f"{rng.choice(('VRL', 'Gati', 'Shree Maruti', 'TCI'))} Roadways"
    taxable = _amount(rng, 3000, 35000)
    return {
        "seller_name": name,
        "buyer_name": c.name,
        "buyer_gstin": c.gstin,
        "item_name": "Freight charges (GTA)",
        "hsn_sac": "996511",
        "taxable_value": taxable,
        "total_amount": taxable,
        "reverse_charge": "Yes",
        "invoice_number": f"LR-{rng.randint(10000, 99999)}",
        "invoice_date": d,
        "vehicle_number": _vehicle(rng),
        "narration": _pick(rng, "Transport charges, GST under reverse charge", "Lorry freight", ""),
    }


# --- cross-border --------------------------------------------------------------------------

_FX = {"USD": 83.5, "EUR": 90.2, "GBP": 105.4, "JPY": 0.56, "AED": 22.7, "CNY": 11.6, "AUD": 55.1}


def _fx(cur: str, rng: random.Random) -> float:
    return round(_FX[cur] * rng.uniform(0.98, 1.02), 4)


@template("Import", core=("seller_name", "currency", "bill_of_entry"))
def import_goods_boe(c, rng, d):
    p = c.party("foreign", rng)
    row: Row = {"seller_name": p.name, "buyer_name": c.name, "buyer_gstin": c.gstin}
    row |= _goods(c, rng)
    fx = _fx(p.currency, rng)
    fc_value = round(row["taxable_value"] / fx, 2)
    duty = round(row["taxable_value"] * rng.choice((0.075, 0.1, 0.15)), 2)
    return row | {
        "invoice_number": f"{p.prefix}-{rng.randint(10000, 99999)}",
        "invoice_date": d,
        "currency": p.currency,
        "exchange_rate": fx,
        "rate": round(fc_value / row["quantity"], 4),
        "total_amount": fc_value,
        "customs_duty": duty,
        "igst": round((row["taxable_value"] + duty) * 0.18, 2),
        "bill_of_entry": f"{rng.randint(10**6, 10**7 - 1)}",
        "port_code": _pick(rng, "INNSA1", "INMAA1", "INMUN1", "INBOM4"),
        "country": p.country,
        "narration": _pick(rng, "Import shipment", "Material imported", ""),
    }


@template("Import", core=("seller_name", "bill_of_entry"))
def import_inr_booked(c, rng, d):
    p = c.party("foreign", rng)
    row: Row = {"seller_name": p.name, "buyer_name": c.name}
    row |= _goods(c, rng)
    duty = round(row["taxable_value"] * 0.1, 2)
    return row | {
        "invoice_number": f"{p.prefix}/{rng.randint(1000, 9999)}",
        "invoice_date": d,
        "currency": "INR",
        "customs_duty": duty,
        "igst": round((row["taxable_value"] + duty) * 0.18, 2),
        "total_amount": round(row["taxable_value"] + duty, 2),
        "bill_of_entry": f"BE{rng.randint(10**6, 10**7 - 1)}",
        "iec": f"{rng.randint(10**9, 10**10 - 1)}",
        "narration": _pick(rng, "Landed cost booked in INR", "Clearing through CHA", ""),
    }


@template("Import", heldout=True, core=("seller_name", "currency"))
def import_without_boe_number(c, rng, d):
    p = c.party("foreign", rng)
    row: Row = {"seller_name": p.name, "buyer_name": c.name, "buyer_gstin": c.gstin}
    row |= _goods(c, rng)
    fx = _fx(p.currency, rng)
    return row | {
        "invoice_number": f"PI-{rng.randint(1000, 9999)}",
        "invoice_date": d,
        "currency": p.currency,
        "exchange_rate": fx,
        "total_amount": round(row["taxable_value"] / fx, 2),
        "customs_duty": round(row["taxable_value"] * 0.075, 2),
        "country": p.country,
        "narration": _pick(rng, "Consignment from overseas supplier", "Inbound sea freight", ""),
    }


@template("Export", core=("buyer_name", "currency", "shipping_bill"))
def export_under_lut(c, rng, d):
    p = c.party("foreign", rng)
    row: Row = {"seller_name": c.name, "seller_gstin": c.gstin, "buyer_name": p.name}
    row |= _goods(c, rng)
    fx = _fx(p.currency, rng)
    return row | {
        "invoice_number": c.next_number("EXP", rng),
        "invoice_date": d,
        "currency": p.currency,
        "exchange_rate": fx,
        "total_amount": round(row["taxable_value"] / fx, 2),
        "igst": 0.0,
        "lut": f"AD{c.state}0{rng.randint(10**6, 10**7 - 1)}",
        "shipping_bill": f"{rng.randint(10**6, 10**7 - 1)}",
        "port_code": _pick(rng, "INNSA1", "INMUN1", "INMAA1"),
        "country": p.country,
        "narration": _pick(
            rng,
            "Supply meant for export under LUT without payment of IGST",
            "Export invoice",
            "FOB value",
            "",
        ),
    }


@template("Export", core=("buyer_name", "currency"))
def export_with_igst(c, rng, d):
    p = c.party("foreign", rng)
    row: Row = {"seller_name": c.name, "seller_gstin": c.gstin, "buyer_name": p.name}
    row |= _goods(c, rng)
    fx = _fx(p.currency, rng)
    return row | {
        "invoice_number": c.next_number("EXP", rng),
        "invoice_date": d,
        "currency": p.currency,
        "exchange_rate": fx,
        "igst": round(row["taxable_value"] * 0.18, 2),
        "total_amount": round(row["taxable_value"] / fx, 2),
        "shipping_bill": f"{rng.randint(10**6, 10**7 - 1)}",
        "country": p.country,
        "narration": _pick(
            rng, "Export with payment of IGST, refund to be claimed", "CIF shipment", ""
        ),
    }


@template("Export", core=("buyer_name", "lut"))
def supply_to_sez(c, rng, d):
    p = c.party("customer", rng)
    row = _sides(c, p) | _goods(c, rng)
    return row | {
        "invoice_number": c.next_number("SEZ", rng),
        "invoice_date": d,
        "currency": "INR",
        "igst": 0.0,
        "total_amount": row["taxable_value"],
        "lut": f"AD{c.state}0{rng.randint(10**6, 10**7 - 1)}",
        "place_of_supply": "SEZ unit",
        "narration": _pick(rng, "Supply to SEZ unit under LUT", "Zero rated supply to SEZ", ""),
    }


@template("Export", heldout=True, core=("buyer_name",))
def deemed_export_eou(c, rng, d):
    p = c.party("customer", rng)
    row = _sides(c, p) | _goods(c, rng)
    row |= _tax(rng, row["taxable_value"], False, 18)
    return row | {
        "invoice_number": c.next_number("DE", rng),
        "invoice_date": d,
        "currency": "INR",
        "narration": _pick(
            rng, "Deemed export to EOU against advance authorisation", "Deemed export supply"
        ),
    }


# --- value corrections ---------------------------------------------------------------------


def _return_row(c: Company, rng: random.Random, seller, buyer, negative: bool) -> Row:
    row = _sides(seller, buyer) | _goods(c, rng)
    row["quantity"] = round(row["quantity"] * rng.choice((0.1, 0.2, 0.25, 0.5)), 2)
    row["taxable_value"] = round(row["quantity"] * row["rate"], 2)
    party = buyer if isinstance(seller, Company) else seller
    row |= _tax(rng, row["taxable_value"], _intra(c, party))
    if negative:
        for f in ("quantity", "taxable_value", "cgst", "sgst", "igst", "total_amount"):
            if f in row:
                row[f] = -row[f]
    return row


@template("Purchase Return / Debit Note", core=("seller_name", "taxable_value", "reference_number"))
def debit_note_negative(c, rng, d):
    p = c.party("supplier", rng)
    row = _return_row(c, rng, p, c, negative=True)
    return row | {
        "invoice_number": c.next_number("DN", rng),
        "invoice_date": d,
        "reference_number": _their_number(p, rng),
        "reason": _pick(
            rng, "Damaged in transit", "Short supply", "Wrong grade supplied", "Goods returned"
        ),
        "narration": _pick(rng, "Goods returned to supplier", "Purchase return", ""),
    }


@template("Purchase Return / Debit Note", core=("seller_name", "reference_number"))
def debit_note_rate_difference(c, rng, d):
    p = c.party("supplier", rng)
    taxable = _amount(rng, 1000, 40000)
    row = _sides(p, c) | {"taxable_value": taxable}
    row |= _tax(rng, taxable, _intra(c, p), 18)
    return row | {
        "invoice_number": c.next_number("DN", rng),
        "invoice_date": d,
        "document_type": "Debit Note",
        "reference_number": _their_number(p, rng),
        "reason": _pick(rng, "Rate difference", "Excess billed", "Price as per PO is lower"),
        "narration": _pick(
            rng, "Debit note issued to supplier for rate difference", "Claim on supplier", ""
        ),
    }


@template("Purchase Return / Debit Note", heldout=True, core=("seller_name", "taxable_value"))
def purchase_return_quality(c, rng, d):
    p = c.party("supplier", rng)
    row = _return_row(c, rng, p, c, negative=True)
    return row | {
        "invoice_number": c.next_number("PR", rng),
        "invoice_date": d,
        "reference_number": f"GRN-{rng.randint(1000, 9999)}",
        "reason": "Quality issue",
    }


@template("Sales Return / Credit Note", core=("buyer_name", "taxable_value", "reference_number"))
def credit_note_negative(c, rng, d):
    p = c.party("customer", rng)
    row = _return_row(c, rng, c, p, negative=True)
    return row | {
        "invoice_number": c.next_number("CN", rng),
        "invoice_date": d,
        "reference_number": f"{c.prefix}/S/{rng.randint(100, 999):04d}",
        "reason": _pick(
            rng,
            "Damaged goods returned by customer",
            "Excess quantity returned",
            "Wrong item delivered",
        ),
        "narration": _pick(rng, "Sales return", "Goods received back from customer", ""),
    }


@template("Sales Return / Credit Note", core=("buyer_name", "reference_number"))
def credit_note_discount(c, rng, d):
    p = c.party("customer", rng)
    taxable = _amount(rng, 1000, 50000)
    row = _sides(c, p) | {"taxable_value": taxable}
    row |= _tax(rng, taxable, _intra(c, p), 18)
    return row | {
        "invoice_number": c.next_number("CN", rng),
        "invoice_date": d,
        "document_type": "Credit Note",
        "reference_number": f"{c.prefix}/S/{rng.randint(100, 999):04d}",
        "reason": _pick(rng, "Post-sale discount", "Quantity discount", "Rate revision"),
        "narration": _pick(rng, "Credit note for discount allowed", "Turnover discount Q2", ""),
    }


@template("Sales Return / Credit Note", heldout=True, core=("buyer_name", "taxable_value"))
def sales_return_unreferenced(c, rng, d):
    p = c.party("customer", rng)
    row = _return_row(c, rng, c, p, negative=True)
    return row | {
        "invoice_number": c.next_number("SR", rng),
        "invoice_date": d,
        "narration": _pick(rng, "Material came back, customer refused", ""),
    }


# --- money movements -----------------------------------------------------------------------


@template("Payment", core=("debit_account", "credit_account", "total_amount"))
def payment_to_supplier(c, rng, d):
    p = c.party(rng.choice(("supplier", "vendor")), rng)
    mode = _pick(rng, "NEFT", "RTGS", "IMPS")
    return {
        "invoice_number": c.next_number("PMT", rng),
        "invoice_date": d,
        "debit_account": p.name,
        "credit_account": _bank(c, rng),
        "total_amount": _amount(rng, 5000, 900000),
        "payment_mode": mode,
        "payment_reference": _utr(rng, mode),
        "reference_number": _their_number(p, rng),
        "narration": _pick(
            rng, "Paid against bill", f"Payment to {p.name}", "Being amount paid", ""
        ),
    }


@template("Payment", core=("debit_account", "credit_account"))
def payment_petty_cash(c, rng, d):
    head = _pick(
        rng, "Conveyance", "Staff Welfare", "Printing & Stationery", "Tea & Refreshment", "Postage"
    )
    return {
        "invoice_number": c.next_number("CP", rng),
        "invoice_date": d,
        "debit_account": head,
        "credit_account": c.cash,
        "total_amount": _amount(rng, 100, 6000),
        "payment_mode": "Cash",
        "narration": _pick(rng, f"{head} paid in cash", "Petty expenses", ""),
    }


@template("Payment", heldout=True, core=("debit_account", "credit_account"))
def payment_statutory_dues(c, rng, d):
    head = _pick(rng, "GST Payable", "TDS Payable", "PF Payable", "Professional Tax Payable")
    return {
        "invoice_number": c.next_number("PMT", rng),
        "invoice_date": d,
        "debit_account": head,
        "credit_account": _bank(c, rng),
        "total_amount": _amount(rng, 2000, 300000),
        "payment_mode": "Net banking",
        "payment_reference": f"CIN{rng.randint(10**12, 10**13 - 1)}",
        "narration": _pick(rng, f"{head} deposited for {d:%b}", "Challan paid", ""),
    }


@template("Receipt", core=("debit_account", "credit_account", "total_amount"))
def receipt_from_customer(c, rng, d):
    p = c.party("customer", rng)
    mode = _pick(rng, "NEFT", "RTGS", "IMPS", "Cheque")
    return {
        "invoice_number": c.next_number("RCT", rng),
        "invoice_date": d,
        "debit_account": _bank(c, rng),
        "credit_account": p.name,
        "total_amount": _amount(rng, 5000, 900000),
        "payment_mode": mode,
        "payment_reference": _utr(rng, mode),
        "reference_number": f"{c.prefix}/S/{rng.randint(100, 999):04d}",
        "narration": _pick(
            rng,
            "Received against invoice",
            f"Amount received from {p.name}",
            "Being payment received",
            "",
        ),
    }


@template("Receipt", core=("debit_account", "credit_account"))
def receipt_cash_from_customer(c, rng, d):
    p = c.party("customer", rng)
    return {
        "invoice_number": c.next_number("CR", rng),
        "invoice_date": d,
        "debit_account": c.cash,
        "credit_account": p.name,
        "total_amount": _amount(rng, 1000, 150000),
        "payment_mode": "Cash",
        "narration": _pick(rng, "Cash received", "Part payment received in cash", ""),
    }


@template("Receipt", heldout=True, core=("debit_account", "credit_account"))
def receipt_other_income(c, rng, d):
    head = _pick(rng, "Interest on FD", "Scrap Sales", "Rent Received", "Insurance Claim Received")
    return {
        "invoice_number": c.next_number("RCT", rng),
        "invoice_date": d,
        "debit_account": _bank(c, rng),
        "credit_account": head,
        "total_amount": _amount(rng, 1000, 250000),
        "payment_mode": "NEFT",
        "narration": _pick(rng, f"{head} credited by bank", "Credit as per bank statement", ""),
    }


@template("Contra", core=("debit_account", "credit_account"))
def contra_cash_deposit(c, rng, d):
    return {
        "invoice_number": c.next_number("CON", rng),
        "invoice_date": d,
        "debit_account": _bank(c, rng),
        "credit_account": c.cash,
        "total_amount": _amount(rng, 5000, 400000),
        "narration": _pick(rng, "Cash deposited in bank", "Being cash deposited", ""),
    }


@template("Contra", core=("debit_account", "credit_account"))
def contra_bank_transfer(c, rng, d):
    src, dst = rng.sample(c.banks, 2)
    mode = _pick(rng, "NEFT", "RTGS")
    return {
        "invoice_number": c.next_number("CON", rng),
        "invoice_date": d,
        "debit_account": dst,
        "credit_account": src,
        "total_amount": _amount(rng, 50000, 2500000),
        "payment_mode": mode,
        "payment_reference": _utr(rng, mode),
        "narration": _pick(rng, "Fund transfer between own accounts", "Transfer", ""),
    }


@template("Contra", heldout=True, core=("debit_account", "credit_account"))
def contra_cash_withdrawal(c, rng, d):
    return {
        "invoice_number": c.next_number("CON", rng),
        "invoice_date": d,
        "debit_account": c.cash,
        "credit_account": _bank(c, rng),
        "total_amount": _amount(rng, 2000, 200000),
        "payment_mode": "Self cheque",
        "payment_reference": _utr(rng, "Cheque"),
        "narration": _pick(rng, "Cash withdrawn for office use", "Self", ""),
    }


@template("Journal", core=("debit_account", "credit_account"))
def journal_depreciation(c, rng, d):
    asset = _pick(rng, "Plant & Machinery", "Furniture & Fixtures", "Computers", "Vehicles")
    return {
        "invoice_number": c.next_number("JV", rng),
        "invoice_date": d,
        "debit_account": "Depreciation",
        "credit_account": asset,
        "total_amount": _amount(rng, 5000, 400000),
        "narration": _pick(
            rng, f"Depreciation on {asset} for H1", "Being depreciation provided", ""
        ),
    }


@template("Journal", core=("debit_account", "credit_account"))
def journal_provision_tds(c, rng, d):
    p = c.party("vendor", rng)
    dr, cr = rng.choice(
        (
            ("Audit Fees", "Provision for Audit Fees"),
            (p.name, "TDS Payable 194C"),
            (p.name, "TDS Payable 194J"),
            ("Bonus", "Bonus Payable"),
        )
    )
    return {
        "invoice_number": c.next_number("JV", rng),
        "invoice_date": d,
        "debit_account": dr,
        "credit_account": cr,
        "total_amount": _amount(rng, 1000, 200000),
        "narration": _pick(
            rng, "Provision for the month", "TDS deducted on bill", "Year-end accrual", ""
        ),
    }


@template("Journal", core=("debit_account", "credit_account"))
def journal_party_setoff(c, rng, d):
    s, cu = c.party("supplier", rng), c.party("customer", rng)
    return {
        "invoice_number": c.next_number("JV", rng),
        "invoice_date": d,
        "debit_account": s.name,
        "credit_account": cu.name,
        "total_amount": _amount(rng, 5000, 300000),
        "narration": _pick(rng, "Set off of receivable against payable", "Contra adjustment", ""),
    }


@template("Journal", heldout=True, core=("debit_account", "credit_account"))
def journal_gst_setoff(c, rng, d):
    return {
        "invoice_number": c.next_number("JV", rng),
        "invoice_date": d,
        "debit_account": _pick(rng, "Output CGST", "Output SGST", "Output IGST"),
        "credit_account": _pick(rng, "Input CGST", "Input SGST", "Input IGST"),
        "total_amount": _amount(rng, 5000, 500000),
        "narration": _pick(rng, f"ITC utilised for GSTR-3B {d:%b %Y}", "Being ITC set off", ""),
    }


@template("Advance / Prepayment", core=("debit_account", "credit_account", "order_number"))
def advance_to_supplier(c, rng, d):
    p = c.party("supplier", rng)
    mode = _pick(rng, "NEFT", "RTGS")
    return {
        "invoice_number": c.next_number("PMT", rng),
        "invoice_date": d,
        "debit_account": p.name,
        "credit_account": _bank(c, rng),
        "total_amount": _amount(rng, 10000, 500000),
        "payment_mode": mode,
        "payment_reference": _utr(rng, mode),
        "order_number": f"{c.prefix}/PO/{rng.randint(100, 999)}",
        "narration": _pick(
            rng,
            "Advance against PO",
            "30% advance as per terms",
            "Token amount paid before supply",
            "",
        ),
    }


@template("Advance / Prepayment", core=("debit_account", "credit_account", "order_number"))
def advance_from_customer(c, rng, d):
    p = c.party("customer", rng)
    mode = _pick(rng, "NEFT", "RTGS", "Cheque")
    return {
        "invoice_number": c.next_number("RCT", rng),
        "invoice_date": d,
        "debit_account": _bank(c, rng),
        "credit_account": p.name,
        "total_amount": _amount(rng, 10000, 500000),
        "payment_mode": mode,
        "payment_reference": _utr(rng, mode),
        "order_number": f"{p.prefix}/PO/{rng.randint(100, 999)}",
        "narration": _pick(rng, "Advance received against order", "Booking amount received", ""),
    }


@template("Advance / Prepayment", heldout=True, core=("debit_account", "credit_account"))
def prepaid_expense(c, rng, d):
    head = _pick(rng, "Prepaid Insurance", "Prepaid AMC", "Prepaid Rent")
    return {
        "invoice_number": c.next_number("PMT", rng),
        "invoice_date": d,
        "debit_account": head,
        "credit_account": _bank(c, rng),
        "total_amount": _amount(rng, 10000, 300000),
        "payment_mode": "NEFT",
        "narration": _pick(
            rng, "Annual premium paid for next 12 months", "Paid in advance for the year", ""
        ),
    }


# --- people --------------------------------------------------------------------------------


@template("Salary / Payroll", core=("employee_name", "net_pay"))
def payroll_payslip(c, rng, d):
    e = rng.choice(c.employees)
    hra = round(e.basic * 0.4, 0)
    gross = e.basic + hra + rng.choice((0, 1600, 2500))
    pf = round(min(e.basic, 15000) * 0.12, 0)
    esi = round(gross * 0.0075, 0) if gross <= 21000 else 0.0
    return {
        "invoice_number": f"PAY/{_period(d)}/{e.emp_id}",
        "invoice_date": d,
        "employee_id": e.emp_id,
        "employee_name": e.name,
        "pay_period": _period(d),
        "basic_pay": float(e.basic),
        "hra": hra,
        "gross_pay": float(gross),
        "pf": pf,
        "esi": esi,
        "net_pay": float(gross - pf - esi),
    }


@template("Salary / Payroll", core=("debit_account", "employee_name"))
def salary_bank_transfer(c, rng, d):
    e = rng.choice(c.employees)
    return {
        "invoice_number": c.next_number("SAL", rng),
        "invoice_date": d,
        "employee_name": e.name,
        "debit_account": "Salary Payable",
        "credit_account": _bank(c, rng),
        "total_amount": float(round(e.basic * 1.3, -2)),
        "payment_mode": "NEFT",
        "narration": _pick(rng, f"Salary for {_period(d)}", "Net salary credited", ""),
    }


@template("Salary / Payroll", heldout=True, core=("employee_name", "net_pay"))
def payroll_with_days(c, rng, d):
    e = rng.choice(c.employees)
    present = rng.randint(20, 26)
    gross = round(e.basic * 1.4 * present / 26, 0)
    return {
        "invoice_number": f"SLIP-{e.emp_id}-{d:%m%y}",
        "invoice_date": d,
        "employee_id": e.emp_id,
        "employee_name": e.name,
        "pay_period": _period(d),
        "days_present": float(present),
        "gross_pay": gross,
        "net_pay": round(gross * 0.9, 0),
    }


@template("Attendance", core=("employee_name", "days_present"))
def attendance_monthly(c, rng, d):
    e = rng.choice(c.employees)
    present = rng.randint(18, 26)
    return {
        "invoice_number": f"ATT/{_period(d)}/{e.emp_id}",
        "invoice_date": d,
        "employee_id": e.emp_id,
        "employee_name": e.name,
        "pay_period": _period(d),
        "days_present": float(present),
        "days_absent": float(26 - present),
        "overtime_hours": float(rng.choice((0, 0, 4, 8, 12, 16))),
    }


@template("Attendance", core=("employee_name", "days_present"))
def attendance_shift(c, rng, d):
    e = rng.choice(c.employees)
    return {
        "invoice_number": f"ATT-{d:%d%m}-{e.emp_id}",
        "invoice_date": d,
        "employee_id": e.emp_id,
        "employee_name": e.name,
        "days_present": 1.0,
        "overtime_hours": float(rng.choice((0, 1, 2, 3))),
        "extra:Shift": _pick(rng, "A", "B", "C", "General"),
        "narration": _pick(rng, "Daily muster", "Shift register", ""),
    }


@template("Attendance", heldout=True, core=("employee_name", "days_absent"))
def attendance_leave(c, rng, d):
    e = rng.choice(c.employees)
    return {
        "invoice_number": f"LV/{e.emp_id}/{rng.randint(10, 99)}",
        "invoice_date": d,
        "employee_name": e.name,
        "days_absent": float(rng.randint(1, 5)),
        "extra:Leave Type": _pick(rng, "CL", "SL", "EL", "LOP"),
        "narration": _pick(rng, "Leave application approved", ""),
    }


# --- orders --------------------------------------------------------------------------------


def _order(c: Company, rng: random.Random, d: date, seller, buyer, series: str) -> Row:
    row = _sides(seller, buyer) | _goods(c, rng)
    number = c.next_number(series, rng)
    return row | {
        "invoice_number": number,
        "invoice_date": d,
        "order_number": number,
        "order_date": d,
        "due_date": d + timedelta(days=rng.choice((7, 15, 21, 30, 45))),
    }


@template("Purchase Order", core=("order_date", "seller_name", "buyer_name"))
def purchase_order(c, rng, d):
    row = _order(c, rng, d, c.party("supplier", rng), c, "PO")
    return row | {
        "gst_rate": rng.choice((5, 12, 18)),
        "narration": _pick(
            rng, "PO raised", "Order placed as per quotation", "Delivery within 15 days", ""
        ),
    }


@template("Purchase Order", core=("due_date", "seller_name"))
def purchase_order_terms(c, rng, d):
    row = _order(c, rng, d, c.party("supplier", rng), c, "PO")
    row.pop("taxable_value")
    return row | {
        "narration": _pick(
            rng, "Payment terms 30 days from delivery", "Order for next month's requirement", ""
        )
    }


@template("Purchase Order", heldout=True, core=("seller_name", "rate"))
def rate_contract_po(c, rng, d):
    row = _order(c, rng, d, c.party("supplier", rng), c, "RC")
    row.pop("taxable_value")
    row.pop("order_date")
    return row | {"narration": "Annual rate contract, call-off as needed"}


@template("Sales Order", core=("order_date", "seller_name", "buyer_name"))
def sales_order(c, rng, d):
    row = _order(c, rng, d, c, c.party("customer", rng), "SO")
    return row | {
        "gst_rate": rng.choice((5, 12, 18)),
        "narration": _pick(
            rng, "Order received", "Customer PO accepted", "Dispatch by due date", ""
        ),
    }


@template("Sales Order", core=("due_date", "buyer_name"))
def sales_order_customer_po(c, rng, d):
    p = c.party("customer", rng)
    row = _order(c, rng, d, c, p, "SO")
    row.pop("taxable_value")
    return row | {
        "reference_number": f"{p.prefix}/PO/{rng.randint(100, 999)}",
        "narration": _pick(rng, "Against customer purchase order", ""),
    }


@template("Sales Order", heldout=True, core=("buyer_name", "due_date"))
def sales_order_schedule(c, rng, d):
    row = _order(c, rng, d, c, c.party("customer", rng), "SCH")
    row.pop("order_date")
    return row | {"narration": "Monthly delivery schedule from customer"}


@template("Job Work Out Order", core=("job_worker", "process"))
def job_work_out_order(c, rng, d):
    p = c.party("job_worker", rng)
    row = _order(c, rng, d, p, c, "JWO")
    row.pop("taxable_value")
    return row | {
        "rate": round(rng.uniform(2, 60), 2),
        "job_worker": p.name,
        "process": rng.choice(JOB_PROCESSES),
        "narration": _pick(rng, "Job work order issued", "Processing charges per kg", ""),
    }


@template("Job Work Out Order", heldout=True, core=("seller_name", "process"))
def job_work_out_order_no_worker_field(c, rng, d):
    row = _order(c, rng, d, c.party("job_worker", rng), c, "JWO")
    row.pop("taxable_value")
    return row | {"process": rng.choice(JOB_PROCESSES), "narration": "Outsourced processing order"}


@template("Job Work In Order", core=("process", "buyer_name"))
def job_work_in_order(c, rng, d):
    p = c.party("principal", rng)
    row = _order(c, rng, d, c, p, "JWI")
    row.pop("taxable_value")
    return row | {
        "rate": round(rng.uniform(2, 60), 2),
        "order_number": f"{p.prefix}/JW/{rng.randint(100, 999)}",
        "process": rng.choice(JOB_PROCESSES),
        "narration": _pick(
            rng,
            "Job work order received from principal",
            "Material to be supplied by principal",
            "",
        ),
    }


@template("Job Work In Order", heldout=True, core=("buyer_name", "process"))
def job_work_in_order_itc04(c, rng, d):
    row = _order(c, rng, d, c, c.party("principal", rng), "JWI")
    row.pop("taxable_value")
    return row | {
        "process": rng.choice(JOB_PROCESSES),
        "narration": "Conversion order, ITC-04 applicable to principal",
    }


# --- inventory movements -------------------------------------------------------------------


@template("Receipt Note", core=("grn_number", "quantity"))
def grn(c, rng, d):
    row = _sides(c.party("supplier", rng), c) | _goods(c, rng, valued=False)
    num = c.next_number("GRN", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "grn_number": num,
        "order_number": f"{c.prefix}/PO/{rng.randint(100, 999)}",
        "vehicle_number": _vehicle(rng),
        "godown": rng.choice(c.godowns),
        "narration": _pick(
            rng, "Material received", "Inward as per PO", "Received in good order", ""
        ),
    }


@template("Receipt Note", core=("challan_number", "quantity"))
def grn_against_supplier_challan(c, rng, d):
    p = c.party("supplier", rng)
    row = _sides(p, c) | _goods(c, rng, valued=False)
    num = c.next_number("MRN", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "grn_number": num,
        "challan_number": f"{p.prefix}/DC/{rng.randint(10, 999)}",
        "narration": _pick(
            rng, "Received against supplier's delivery challan", "Inward entry, bill awaited", ""
        ),
    }


@template("Receipt Note", heldout=True, core=("grn_number", "rate"))
def grn_valued(c, rng, d):
    row = _sides(c.party("supplier", rng), c) | _goods(c, rng)
    num = c.next_number("GRN", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "grn_number": num,
        "narration": "Inward at PO rate, invoice pending",
    }


@template("Delivery Note", core=("challan_number", "quantity"))
def delivery_challan(c, rng, d):
    row = _sides(c, c.party("customer", rng)) | _goods(c, rng, valued=False)
    num = c.next_number("DC", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "challan_number": num,
        "vehicle_number": _vehicle(rng),
        "eway_bill": f"{rng.randint(10**11, 10**12 - 1)}",
        "order_number": f"{c.prefix}/SO/{rng.randint(100, 999)}",
        "narration": _pick(rng, "Goods dispatched", "Delivery against SO", "Sent per challan", ""),
    }


@template("Delivery Note", core=("challan_number", "taxable_value"))
def delivery_challan_valued(c, rng, d):
    row = _sides(c, c.party("customer", rng)) | _goods(c, rng)
    num = c.next_number("DC", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "challan_number": num,
        "eway_bill": f"{rng.randint(10**11, 10**12 - 1)}",
        "narration": _pick(
            rng, "Value for e-way bill only, invoice to follow", "Delivery challan", ""
        ),
    }


@template("Delivery Note", heldout=True, core=("vehicle_number", "quantity"))
def dispatch_with_lr(c, rng, d):
    row = _sides(c, c.party("customer", rng)) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("DSP", rng),
        "invoice_date": d,
        "vehicle_number": f"LR {rng.randint(10000, 99999)}",
        "godown": rng.choice(c.godowns),
        "narration": "Dispatched through transporter",
    }


@template("Rejection In", core=("reason", "quantity", "buyer_name"))
def rejection_in(c, rng, d):
    row = _sides(c, c.party("customer", rng)) | _goods(c, rng, valued=False)
    row["quantity"] = round(row["quantity"] * rng.choice((0.05, 0.1, 0.2)), 2)
    return row | {
        "invoice_number": c.next_number("RJI", rng),
        "invoice_date": d,
        "reference_number": f"{c.prefix}/DC/{rng.randint(100, 999):04d}",
        "reason": _pick(
            rng, "Rejected by customer QC", "Dimension out of tolerance", "Surface defects"
        ),
        "narration": _pick(
            rng, "Rejected material received back from customer", "Rejection in", ""
        ),
    }


@template("Rejection In", heldout=True, core=("godown", "quantity"))
def rejection_in_store(c, rng, d):
    row = _sides(c, c.party("customer", rng)) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("RJI", rng),
        "invoice_date": d,
        "godown": "Rejection Store",
        "narration": "Customer sent back lot, kept in rejection store",
    }


@template("Rejection Out", core=("reason", "quantity", "seller_name"))
def rejection_out(c, rng, d):
    row = _sides(c.party("supplier", rng), c) | _goods(c, rng, valued=False)
    row["quantity"] = round(row["quantity"] * rng.choice((0.05, 0.1, 0.2)), 2)
    num = c.next_number("RJO", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "challan_number": num,
        "reference_number": f"GRN-{rng.randint(1000, 9999)}",
        "reason": _pick(rng, "Failed incoming inspection", "QC fail - hardness", "Wrong grade"),
        "narration": _pick(rng, "Rejected material returned to supplier", "Rejection out", ""),
    }


@template("Rejection Out", heldout=True, core=("seller_name", "quantity"))
def rejection_out_replacement(c, rng, d):
    row = _sides(c.party("supplier", rng), c) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("RJO", rng),
        "invoice_date": d,
        "vehicle_number": _vehicle(rng),
        "narration": "Sent back to vendor for replacement, no debit note",
    }


@template("Stock Journal", core=("godown", "destination_godown"))
def godown_transfer(c, rng, d):
    src, dst = rng.sample(c.godowns, 2)
    return _goods(c, rng, valued=False) | {
        "invoice_number": c.next_number("STJ", rng),
        "invoice_date": d,
        "godown": src,
        "destination_godown": dst,
        "narration": _pick(rng, "Inter-godown transfer", "Shifted to production", ""),
    }


@template("Stock Journal", core=("item_name", "quantity"))
def production_consumption(c, rng, d):
    return _goods(c, rng, valued=False) | {
        "invoice_number": c.next_number("MFG", rng),
        "invoice_date": d,
        "godown": rng.choice(c.godowns),
        "narration": _pick(
            rng,
            "Raw material consumed for production",
            "Conversion to finished goods",
            "Manufacturing journal",
        ),
    }


@template("Stock Journal", heldout=True, core=("quantity",))
def branch_stock_transfer(c, rng, d):
    return _goods(c, rng, valued=False) | {
        "invoice_number": c.next_number("BST", rng),
        "invoice_date": d,
        "godown": rng.choice(c.godowns),
        "narration": "Stock moved to branch within same GSTIN",
    }


@template("Physical Stock", core=("physical_quantity",))
def physical_count(c, rng, d):
    row = _goods(c, rng, valued=False)
    book = row.pop("quantity")
    return row | {
        "invoice_number": c.next_number("PHY", rng),
        "invoice_date": d,
        "godown": rng.choice(c.godowns),
        "book_quantity": book,
        "physical_quantity": round(book * rng.uniform(0.95, 1.02), 2),
        "narration": _pick(rng, "Physical verification", "Month-end stock count", ""),
    }


@template("Physical Stock", core=("physical_quantity",))
def physical_count_no_book(c, rng, d):
    row = _goods(c, rng, valued=False)
    row["physical_quantity"] = row.pop("quantity")
    return row | {
        "invoice_number": c.next_number("PHY", rng),
        "invoice_date": d,
        "godown": rng.choice(c.godowns),
        "narration": _pick(rng, "Stock taking", "Annual stock audit", ""),
    }


@template("Physical Stock", heldout=True, core=("godown",))
def physical_variance(c, rng, d):
    row = _goods(c, rng, valued=False)
    qty = row.pop("quantity")
    return row | {
        "invoice_number": c.next_number("PHY", rng),
        "invoice_date": d,
        "godown": rng.choice(c.godowns),
        "physical_quantity": qty,
        "extra:Variance": round(qty * rng.uniform(-0.05, 0.02), 2),
        "narration": "Cycle count",
    }


@template("Material Out", core=("job_worker", "quantity"))
def material_out_to_job_worker(c, rng, d):
    p = c.party("job_worker", rng)
    row = _sides(c, p) | _goods(c, rng, valued=False)
    num = c.next_number("MO", rng)
    return row | {
        "invoice_number": num,
        "invoice_date": d,
        "challan_number": num,
        "job_worker": p.name,
        "process": rng.choice(JOB_PROCESSES),
        "narration": _pick(
            rng,
            "Sent for job work",
            "Material issued to job worker",
            "Under job work challan, Rule 45",
            "",
        ),
    }


@template("Material Out", heldout=True, core=("buyer_name", "process"))
def material_returned_to_principal(c, rng, d):
    row = _sides(c, c.party("principal", rng)) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("MO", rng),
        "invoice_date": d,
        "process": rng.choice(JOB_PROCESSES),
        "narration": "Processed goods returned to principal",
    }


@template("Material In", core=("job_worker", "quantity"))
def material_in_from_job_worker(c, rng, d):
    p = c.party("job_worker", rng)
    row = _sides(p, c) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("MI", rng),
        "invoice_date": d,
        "challan_number": f"{p.prefix}/DC/{rng.randint(10, 999)}",
        "job_worker": p.name,
        "process": rng.choice(JOB_PROCESSES),
        "narration": _pick(
            rng, "Received back after processing", "Material in from job worker", ""
        ),
    }


@template("Material In", core=("seller_name", "process"))
def material_in_from_principal(c, rng, d):
    p = c.party("principal", rng)
    row = _sides(p, c) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("MI", rng),
        "invoice_date": d,
        "challan_number": f"{p.prefix}/JW/{rng.randint(10, 999)}",
        "process": rng.choice(JOB_PROCESSES),
        "narration": _pick(rng, "Principal's material received for job work", ""),
    }


@template("Material In", heldout=True, core=("seller_name", "quantity"))
def material_in_scrap_return(c, rng, d):
    row = _sides(c.party("job_worker", rng), c) | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("MI", rng),
        "invoice_date": d,
        "reference_number": f"{c.prefix}/MO/{rng.randint(100, 999):04d}",
        "narration": "Balance material and scrap returned by processor",
    }


# --- fallback ------------------------------------------------------------------------------


@template("Other / Miscellaneous", core=("narration",))
def memorandum_sample(c, rng, d):
    row = {"buyer_name": c.party("customer", rng).name} | _goods(c, rng, valued=False)
    return row | {
        "invoice_number": c.next_number("MEMO", rng),
        "invoice_date": d,
        "narration": _pick(
            rng, "Memorandum: free samples handed over", "Memo entry, not to be posted"
        ),
    }


@template("Other / Miscellaneous", core=("narration",))
def cancelled_voucher(c, rng, d):
    return {
        "invoice_number": c.next_number(rng.choice(("S", "PMT", "JV")), rng),
        "invoice_date": d,
        "total_amount": 0.0,
        "narration": _pick(rng, "Cancelled", "Voucher cancelled - duplicate", "VOID"),
    }


@template("Other / Miscellaneous", core=("narration", "debit_account"))
def opening_balance(c, rng, d):
    p = c.party(rng.choice(("customer", "supplier")), rng)
    return {
        "invoice_number": c.next_number("OB", rng),
        "invoice_date": date(2026, 4, 1),
        "debit_account": p.name,
        "total_amount": _amount(rng, 5000, 500000),
        "narration": "Opening balance as on 01-04-2026",
    }


@template("Other / Miscellaneous", heldout=True, core=("narration",))
def optional_voucher(c, rng, d):
    return {
        "invoice_number": c.next_number("OPT", rng),
        "invoice_date": d,
        "debit_account": _pick(rng, "Marketing Budget", "Capex Plan"),
        "total_amount": _amount(rng, 10000, 900000),
        "narration": "Optional voucher for budgeting, does not affect books",
    }


for _label, _templates in TEMPLATES.items():
    assert any(not t.heldout for t in _templates), f"{_label}: no template for seen splits"
