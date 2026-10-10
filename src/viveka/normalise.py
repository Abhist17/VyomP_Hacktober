"""Parsers for Indian number, date and code formats. Every parser returns None for unknown."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

_EXCEL_EPOCH = date(1899, 12, 30)
_DATE_FORMATS = (
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%b-%y",
    "%d %B %Y",
)
_DRCR = re.compile(r"\s*\b(dr|cr)\.?\s*$", re.IGNORECASE)
_CURRENCY = re.compile(r"(₹|rs\.?|inr|usd|eur|\$|€|£)", re.IGNORECASE)


def is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip().lower() in {
        "",
        "-",
        "--",
        "na",
        "n/a",
        "nil",
        "null",
        "none",
        "nan",
    }


def split_drcr(value: object) -> tuple[object, str | None]:
    """Split a trailing Dr/Cr marker: '1,234.00 Cr' -> ('1,234.00', 'Cr')."""
    if not isinstance(value, str):
        return value, None
    match = _DRCR.search(value)
    if not match:
        return value, None
    return value[: match.start()], match.group(1).capitalize()


def parse_amount(value: object) -> float | None:
    """Parse '₹1,23,456.00', '(1,234)', '-500', '1,234 Dr' and plain numbers."""
    if is_blank(value) or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text, _ = split_drcr(str(value))
    text = _CURRENCY.sub("", str(text)).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace(" ", "")
    if text.endswith("-"):
        negative, text = True, text[:-1]
    try:
        amount = float(text)
    except ValueError:
        return None
    return -amount if negative else amount


def parse_date(value: object) -> date | None:
    """Parse day-first dates, ISO dates, datetimes and Excel serial numbers."""
    if is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        if 20000 <= value <= 80000:
            return _EXCEL_EPOCH + timedelta(days=int(value))
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", text):
        return parse_date(float(text))
    text = text.split("T")[0].removesuffix(" 00:00:00")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def code_kind(value: object) -> str | None:
    """Classify an HSN/SAC code: SAC codes are 6 digits starting with 99."""
    if is_blank(value):
        return None
    digits = re.sub(r"\D", "", str(value).split(".")[0])
    if not 2 <= len(digits) <= 8:
        return None
    if digits.startswith("99") and len(digits) == 6:
        return "SAC"
    return "HSN"


def norm_text(value: object) -> str:
    """Lowercased, whitespace-collapsed text; '' for blanks."""
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()
