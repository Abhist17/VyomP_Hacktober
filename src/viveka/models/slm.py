"""SLM adjudicator: Gemma 4 E4B (+ LoRA) scoring the 27 exact label strings.

Plan (block 1): prefill the cached static prefix (instructions + contrastive label
definitions), append the evidence card and row, then score each label continuation's
log-probability. Decoding is grammar-constrained (GBNF in llama.cpp, XGrammar in vLLM)
so a generated answer is always one of the 27 strings.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from viveka.labels import LABELS
from viveka.normalise import is_blank
from viveka.signals import EvidenceCard

SYSTEM_PROMPT = """You are an Indian chartered accountant booking transactions in TallyPrime
for one company.
Pick exactly one voucher type for the transaction, from the company's own books.
Decide from structure, not keywords: whose books these are, which legs are the company's own
cash or bank accounts, whether goods, money or only documents moved, and whether the supply
crossed India's border. Answer with the voucher type only."""


def row_text(row: Mapping[str, object]) -> str:
    """Compact `field: value` serialisation of the non-empty canonical and extra fields."""
    parts = [
        f"{str(k).removeprefix('extra:')}: {v}"
        for k, v in row.items()
        if not str(k).startswith("_") and not is_blank(v)
    ]
    return "\n".join(parts)


def build_prompt(card: EvidenceCard, row: Mapping[str, object], precedents: str = "") -> str:
    labels = "\n".join(f"- {label}" for label in LABELS)
    sections = [
        SYSTEM_PROMPT,
        f"Voucher types:\n{labels}",
        f"Precedents:\n{precedents}" if precedents else "",
        card.render(),
        f"Transaction:\n{row_text(row)}",
        "Voucher type:",
    ]
    return "\n\n".join(s for s in sections if s)


def label_gbnf() -> str:
    """GBNF grammar that only admits the 27 label strings (llama.cpp)."""
    alts = " | ".join(json.dumps(label) for label in LABELS)
    return f"root ::= {alts}\n"


def label_json_schema() -> dict[str, Any]:
    """JSON schema for structured outputs (vLLM / llama.cpp server)."""
    return {
        "type": "object",
        "properties": {"voucher_type": {"type": "string", "enum": list(LABELS)}},
        "required": ["voucher_type"],
    }


class SLMAdjudicator:
    name = "slm"

    def __init__(self, config: Mapping[str, Any]):
        self.backend = config.get("backend", "llama.cpp")
        self.model = config.get("model", "")
        self.gguf_path = Path(config.get("gguf_path", ""))
        self.adapter = config.get("adapter", "")

    def available(self) -> bool:
        if self.backend == "llama.cpp":
            return self.gguf_path.is_file() and importlib.util.find_spec("llama_cpp") is not None
        if self.backend == "vllm":
            return importlib.util.find_spec("vllm") is not None
        return False

    def score(
        self, cards: Sequence[EvidenceCard], rows: Sequence[Mapping[str, object]]
    ) -> np.ndarray:
        # TODO(block 1): per-label log-prob scoring with prefix caching; softmax over labels.
        raise NotImplementedError("SLM label scoring is implemented at the final (block 1).")
