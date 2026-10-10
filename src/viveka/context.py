"""Dataset-level context: whose books, own cash/bank accounts, document links.

Purchase/Sales and eight other directional pairs flip on `company`, so it is resolved
once per file rather than per row.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from viveka import gstin
from viveka.normalise import is_blank, norm_text

_CASH_BANK = re.compile(
    r"\b(cash|petty cash|bank|a/?c|current|savings?|od|cc|hdfc|icici|sbi|axis|kotak|"
    r"yes bank|idfc|pnb|canara|bob|union bank|indusind)\b"
)
# A GSTIN or name recurring in at least this share of rows is taken as the company.
COMPANY_MIN_SHARE = 0.3


@dataclass
class Context:
    company_gstin: str | None = None
    company_name: str | None = None
    source: str = "unknown"  # profile | inferred | unknown
    own_accounts: set[str] = field(default_factory=set)
    # document number -> row ids that mention it (as their own number or as a reference)
    doc_index: dict[str, list[int]] = field(default_factory=dict)

    def is_company(self, gstin_value: object = None, name: object = None) -> bool | None:
        """Three-valued: True / False when there is evidence, None when unknown."""
        g = gstin.clean(gstin_value) if not is_blank(gstin_value) else None
        if self.company_gstin and g:
            return g == self.company_gstin
        n = norm_text(name)
        if self.company_name and n:
            return n == self.company_name
        return None

    def is_own_account(self, account: object) -> bool | None:
        a = norm_text(account)
        if not a:
            return None
        return a in self.own_accounts


def _most_common_share(values: list[str], n_rows: int) -> str | None:
    if not values or n_rows == 0:
        return None
    value, count = Counter(values).most_common(1)[0]
    return value if count / n_rows >= COMPANY_MIN_SHARE else None


def infer_context(
    rows: list[Mapping[str, object]],
    company_gstin: str | None = None,
    company_name: str | None = None,
    own_accounts: Iterable[str] = (),
) -> Context:
    ctx = Context(own_accounts={norm_text(a) for a in own_accounts if norm_text(a)})
    n = len(rows)

    if company_gstin or company_name:
        ctx.company_gstin = gstin.clean(company_gstin) if company_gstin else None
        ctx.company_name = norm_text(company_name) or None
        ctx.source = "profile"
    else:
        gstins = [
            gstin.clean(r.get(f))
            for r in rows
            for f in ("seller_gstin", "buyer_gstin")
            if gstin.is_valid(r.get(f))
        ]
        names = [
            norm_text(r.get(f))
            for r in rows
            for f in ("seller_name", "buyer_name")
            if norm_text(r.get(f))
        ]
        ctx.company_gstin = _most_common_share(gstins, n)
        ctx.company_name = _most_common_share(names, n)
        if ctx.company_gstin or ctx.company_name:
            ctx.source = "inferred"

    # Own-account registry: ledgers that look like cash/bank. TODO(block 3): require
    # recurrence on the company's side and merge accounts from the business profile.
    for r in rows:
        for f in ("debit_account", "credit_account"):
            a = norm_text(r.get(f))
            if a and _CASH_BANK.search(a):
                ctx.own_accounts.add(a)

    # Document-link index. TODO(block 3): typed edges (invoice, PO, GRN, challan, BoE).
    for r in rows:
        rid = int(r.get("_row_id", 0))
        for f in (
            "invoice_number",
            "reference_number",
            "order_number",
            "challan_number",
            "grn_number",
        ):
            key = norm_text(r.get(f))
            if key:
                ctx.doc_index.setdefault(key, []).append(rid)
    return ctx
