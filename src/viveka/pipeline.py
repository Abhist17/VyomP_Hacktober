"""End-to-end classification: align -> normalise -> context -> evidence -> opinions -> decide."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from viveka import __version__, gstin
from viveka.align import Mapping
from viveka.context import Context, infer_context
from viveka.explain import explain
from viveka.fusion import fuse, prediction_set
from viveka.guardrails import apply as apply_guardrails
from viveka.io import to_canonical
from viveka.labels import LABELS
from viveka.models import OpinionSource
from viveka.models.precedents import PrecedentMemory
from viveka.models.rules import RulesOpinion
from viveka.models.sentinel import Sentinel
from viveka.models.slm import SLMAdjudicator
from viveka.normalise import is_blank, parse_amount, parse_date
from viveka.output import Alternative, EvidenceItem, Prediction
from viveka.policy import Policy, load_policy
from viveka.schema import AMOUNT, DATE, FIELD_KIND, GSTIN, NUMBER
from viveka.signals import EvidenceCard, build_card

MODES = ("fast", "accurate", "deliberate")


def normalise_row(row: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in row.items():
        if is_blank(value):
            out[key] = None
            continue
        kind = FIELD_KIND.get(key)
        if kind in (AMOUNT, NUMBER):
            parsed = parse_amount(value)
            out[key] = parsed if parsed is not None else value
        elif kind == DATE:
            parsed_date = parse_date(value)
            out[key] = parsed_date.isoformat() if parsed_date else value
        elif kind == GSTIN:
            out[key] = gstin.clean(value)
        else:
            out[key] = value
    return out


def _doc_number(value: object) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def default_sources(policy: Policy) -> list[OpinionSource]:
    return [RulesOpinion(policy), SLMAdjudicator(policy.slm), Sentinel(), PrecedentMemory()]


@dataclass
class Run:
    """Everything one classification pass produced, for interfaces that show their working."""

    predictions: list[Prediction]
    rows: list[dict[str, object]]
    cards: list[EvidenceCard]
    context: Context
    mappings: list[Mapping]


def classify(
    df_raw: pd.DataFrame,
    policy: Policy | None = None,
    mode: str = "accurate",
    company_gstin: str | None = None,
    company_name: str | None = None,
    own_accounts: Iterable[str] = (),
    sources: list[OpinionSource] | None = None,
) -> list[Prediction]:
    return run(df_raw, policy, mode, company_gstin, company_name, own_accounts, sources).predictions


def run(
    df_raw: pd.DataFrame,
    policy: Policy | None = None,
    mode: str = "accurate",
    company_gstin: str | None = None,
    company_name: str | None = None,
    own_accounts: Iterable[str] = (),
    sources: list[OpinionSource] | None = None,
) -> Run:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    policy = policy or load_policy()
    sources = [s for s in (sources or default_sources(policy)) if s.available()]

    canonical, mappings = to_canonical(df_raw)
    rows = [normalise_row(r) for r in canonical.to_dict(orient="records")]
    ctx = infer_context(rows, company_gstin, company_name, own_accounts)
    if not rows:
        return Run([], [], [], ctx, mappings)
    cards = [build_card(r, ctx) for r in rows]

    # TODO(block 5): in `fast` mode run the SLM only on rows where the cheap opinions are
    # uncertain or disagree; in `deliberate` mode escalate low-confidence rows.
    opinions = {s.name: s.score(cards, rows) for s in sources}
    fused = fuse(opinions, policy)
    decided_by = "+".join(opinions)

    preds = []
    for row, card, row_probs in zip(rows, cards, fused, strict=True):
        probs, notes = apply_guardrails(row_probs, card)
        top = int(np.argmax(probs))
        pset = prediction_set(probs, policy.coverage)
        alternatives = [
            (LABELS[i], float(probs[i])) for i in np.argsort(-probs)[1:3] if probs[i] >= 0.01
        ]
        confidence = float(probs[top])
        preds.append(
            Prediction(
                row_id=card.row_id,
                invoice_number=_doc_number(row.get("invoice_number")),
                voucher_type=LABELS[top],
                confidence=round(confidence, 4),
                prediction_set=[LABELS[i] for i in pset],
                alternatives=[
                    Alternative(voucher_type=label, probability=round(p, 4))
                    for label, p in alternatives
                ],
                needs_review=len(pset) > 1 or confidence < policy.auto_accept_threshold,
                explanation=explain(LABELS[top], card, alternatives, notes),
                evidence=[
                    EvidenceItem(signal=s.name, value=s.value, fields=list(s.fields))
                    for s in card.true()
                ],
                decided_by=decided_by,
                model_version=f"viveka-{__version__} / {decided_by}",
                policy_version=policy.version,
            )
        )
    return Run(preds, rows, cards, ctx, mappings)
