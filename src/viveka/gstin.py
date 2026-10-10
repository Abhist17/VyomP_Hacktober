"""GSTIN structure and checksum validation.

Layout: 2-digit state code + 10-char PAN + entity code + 'Z' + check character.
The check character is Luhn mod 36 over the first 14 characters.
"""

from __future__ import annotations

import re

_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
# 01-38 are states and union territories; 97 is "other territory", 99 is centre jurisdiction.
_VALID_STATE_CODES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARSET.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _CHARSET[(36 - total % 36) % 36]


def clean(value: object) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", "", str(value)).upper()
    return text or None


def is_valid(value: object) -> bool:
    gstin = clean(value)
    if gstin is None or not _PATTERN.match(gstin):
        return False
    if gstin[:2] not in _VALID_STATE_CODES:
        return False
    return checksum_char(gstin[:14]) == gstin[14]


def state_code(value: object) -> str | None:
    gstin = clean(value)
    return gstin[:2] if gstin and is_valid(gstin) else None


def pan(value: object) -> str | None:
    gstin = clean(value)
    return gstin[2:12] if gstin and is_valid(gstin) else None
