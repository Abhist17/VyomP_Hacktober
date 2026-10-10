"""Schema aligner: map arbitrary headers to the canonical schema.

Stages: (1) synonym dictionary, (2) RapidFuzz similarity, (3) embedding similarity,
(4) SLM constrained to the canonical field list. Stages 3 and 4 are TODO.
Unmapped columns stay available to the SLM as free-text context.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from viveka.schema import SYNONYM_TO_FIELD, normalise_header

FUZZY_THRESHOLD = 88.0


@dataclass(frozen=True)
class Mapping:
    header: str
    field: str | None
    score: float
    stage: str


def _match(header: str) -> Mapping:
    key = normalise_header(header)
    if key in SYNONYM_TO_FIELD:
        return Mapping(header, SYNONYM_TO_FIELD[key], 100.0, "synonym")
    best = process.extractOne(key, SYNONYM_TO_FIELD.keys(), scorer=fuzz.token_sort_ratio)
    if best and best[1] >= FUZZY_THRESHOLD:
        return Mapping(header, SYNONYM_TO_FIELD[best[0]], float(best[1]), "fuzzy")
    # TODO(block 3): embedding stage with Qwen3-Embedding-0.6B, then SLM fallback.
    return Mapping(header, None, 0.0, "unmapped")


def align(headers: list[str], overrides: dict[str, str] | None = None) -> list[Mapping]:
    """Map each header to at most one canonical field; each field is claimed once (best score)."""
    overrides = overrides or {}
    candidates = [
        Mapping(h, overrides[h], 100.0, "override") if h in overrides else _match(h)
        for h in headers
    ]
    claimed: dict[str, Mapping] = {}
    for m in sorted(candidates, key=lambda m: -m.score):
        if m.field and m.field not in claimed:
            claimed[m.field] = m
    winners = {m.header for m in claimed.values()}
    return [
        m if m.header in winners else Mapping(m.header, None, m.score, "unmapped")
        for m in candidates
    ]
