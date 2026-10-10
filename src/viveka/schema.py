"""Canonical transaction schema and header synonyms (stage 1 of the schema aligner).

Synonyms are matched after `normalise_header`, so write them lowercase with single spaces.
Extend this table from the provided Excel during reconnaissance (block 0).
"""

from __future__ import annotations

import re

# Field kinds drive normalisation: amounts, dates, GSTINs, codes and free text.
AMOUNT, DATE, GSTIN, CODE, TEXT, NUMBER = "amount", "date", "gstin", "code", "text", "number"

# fmt: off
CANONICAL: dict[str, tuple[str, tuple[str, ...]]] = {
    # Document identity
    "invoice_number": (TEXT, ("invoice number", "invoice no", "inv no", "bill no", "bill number", "voucher no", "vch no", "document number", "doc no")),
    "invoice_date": (DATE, ("invoice date", "inv date", "bill date", "date", "voucher date", "vch date", "document date", "txn date", "transaction date")),
    "reference_number": (TEXT, ("reference", "reference no", "ref no", "ref", "against ref", "original invoice", "original invoice no", "against invoice")),
    "reference_date": (DATE, ("reference date", "ref date", "original invoice date")),
    "document_type": (TEXT, ("document type", "doc type", "type of document", "transaction type", "txn type")),
    # Parties
    "seller_name": (TEXT, ("seller", "seller name", "supplier", "supplier name", "vendor", "vendor name", "from", "consignor")),
    "seller_gstin": (GSTIN, ("seller gstin", "supplier gstin", "vendor gstin", "gstin of supplier", "from gstin")),
    "buyer_name": (TEXT, ("buyer", "buyer name", "customer", "customer name", "bill to", "to", "consignee", "recipient")),
    "buyer_gstin": (GSTIN, ("buyer gstin", "customer gstin", "recipient gstin", "gstin of recipient", "to gstin")),
    "party_name": (TEXT, ("party", "party name", "particulars", "ledger", "ledger name", "account name", "pty name")),
    "party_gstin": (GSTIN, ("party gstin", "gstin", "gstin/uin", "gst no", "gst number", "pty gstin")),
    "place_of_supply": (TEXT, ("place of supply", "pos", "state of supply")),
    # Items
    "item_name": (TEXT, ("item", "item name", "item description", "description", "product", "goods", "stock item", "माल का नाम")),
    "hsn_sac": (CODE, ("hsn", "hsn code", "sac", "sac code", "hsn/sac", "hsn sac")),
    "quantity": (NUMBER, ("quantity", "qty", "units", "nos")),
    "unit": (TEXT, ("unit", "uom", "unit of measure")),
    "rate": (AMOUNT, ("rate", "unit price", "price", "rate per unit")),
    # Values
    "taxable_value": (AMOUNT, ("taxable value", "taxable amount", "assessable value", "basic amount", "net amount", "value")),
    "discount": (AMOUNT, ("discount", "disc", "discount amount")),
    "freight": (AMOUNT, ("freight", "freight charges", "transport charges", "cartage")),
    "gst_rate": (NUMBER, ("gst rate", "tax rate", "gst %", "rate of tax")),
    "cgst": (AMOUNT, ("cgst", "cgst amount", "central tax")),
    "sgst": (AMOUNT, ("sgst", "sgst amount", "utgst", "state tax")),
    "igst": (AMOUNT, ("igst", "igst amount", "integrated tax")),
    "cess": (AMOUNT, ("cess", "cess amount")),
    "total_amount": (AMOUNT, ("total", "total amount", "invoice value", "invoice amount", "grand total", "amount", "vch amt", "voucher amount", "net payable")),
    "currency": (TEXT, ("currency", "curr", "currency code")),
    "exchange_rate": (NUMBER, ("exchange rate", "fx rate", "conversion rate")),
    "reverse_charge": (TEXT, ("reverse charge", "rcm", "reverse charge applicable")),
    # Money legs
    "debit_account": (TEXT, ("debit account", "dr account", "debit ledger", "account debited", "dr ledger", "by")),
    "credit_account": (TEXT, ("credit account", "cr account", "credit ledger", "account credited", "cr ledger")),
    "debit_amount": (AMOUNT, ("debit", "debit amount", "dr amount", "dr")),
    "credit_amount": (AMOUNT, ("credit", "credit amount", "cr amount", "cr")),
    "payment_mode": (TEXT, ("payment mode", "mode", "mode of payment", "payment method", "instrument")),
    "payment_reference": (TEXT, ("utr", "utr no", "cheque no", "cheque number", "chq no", "transaction id", "txn id", "instrument no")),
    "payment_status": (TEXT, ("payment status", "status", "paid status")),
    "narration": (TEXT, ("narration", "remarks", "remark", "notes", "memo", "comment", "purpose")),
    # Cross-border
    "bill_of_entry": (TEXT, ("bill of entry", "boe", "boe no", "bill of entry no")),
    "shipping_bill": (TEXT, ("shipping bill", "sb no", "shipping bill no")),
    "port_code": (TEXT, ("port code", "port")),
    "customs_duty": (AMOUNT, ("customs duty", "basic customs duty", "bcd")),
    "iec": (TEXT, ("iec", "iec code", "importer exporter code")),
    "lut": (TEXT, ("lut", "lut no", "bond", "lut/bond")),
    "country": (TEXT, ("country", "country of origin", "destination country")),
    # Orders, challans, inventory
    "order_number": (TEXT, ("order no", "order number", "po no", "po number", "so no", "so number", "purchase order", "sales order")),
    "order_date": (DATE, ("order date", "po date", "so date")),
    "due_date": (DATE, ("due date", "delivery date", "expected delivery", "expected date")),
    "challan_number": (TEXT, ("challan no", "challan number", "delivery challan", "dc no", "delivery note no")),
    "grn_number": (TEXT, ("grn", "grn no", "receipt note no", "mrn", "goods receipt note")),
    "eway_bill": (TEXT, ("e-way bill", "eway bill", "ewb no", "e way bill no")),
    "vehicle_number": (TEXT, ("vehicle no", "vehicle number", "lr no", "lorry receipt", "transporter")),
    "godown": (TEXT, ("godown", "warehouse", "location", "store")),
    "destination_godown": (TEXT, ("destination godown", "to godown", "to warehouse")),
    "book_quantity": (NUMBER, ("book quantity", "book qty", "system qty")),
    "physical_quantity": (NUMBER, ("physical quantity", "counted qty", "physical qty", "actual qty")),
    "job_worker": (TEXT, ("job worker", "jobworker", "processor")),
    "process": (TEXT, ("process", "job process", "operation")),
    "reason": (TEXT, ("reason", "return reason", "rejection reason", "reason for issuing note")),
    # People
    "employee_id": (TEXT, ("employee id", "emp id", "emp code", "employee code", "staff id")),
    "employee_name": (TEXT, ("employee", "employee name", "emp name", "staff name")),
    "pay_period": (TEXT, ("pay period", "salary month", "month", "payroll period")),
    "basic_pay": (AMOUNT, ("basic", "basic pay", "basic salary")),
    "hra": (AMOUNT, ("hra", "house rent allowance")),
    "pf": (AMOUNT, ("pf", "epf", "provident fund", "pf deduction")),
    "esi": (AMOUNT, ("esi", "esic", "esi deduction")),
    "gross_pay": (AMOUNT, ("gross", "gross pay", "gross salary", "gross earnings")),
    "net_pay": (AMOUNT, ("net pay", "net salary", "take home")),
    "days_present": (NUMBER, ("days present", "present days", "attendance", "days worked")),
    "days_absent": (NUMBER, ("days absent", "absent days", "leave days", "lop days")),
    "overtime_hours": (NUMBER, ("overtime", "ot hours", "overtime hours")),
}
# fmt: on

FIELD_KIND: dict[str, str] = {name: kind for name, (kind, _) in CANONICAL.items()}


def normalise_header(header: object) -> str:
    text = str(header).strip().lower()
    text = re.sub(r"[_\-./()#:]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


SYNONYM_TO_FIELD: dict[str, str] = {}
for _field, (_kind, _synonyms) in CANONICAL.items():
    SYNONYM_TO_FIELD.setdefault(normalise_header(_field), _field)
    for _syn in _synonyms:
        SYNONYM_TO_FIELD.setdefault(normalise_header(_syn), _field)
