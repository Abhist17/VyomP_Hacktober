"""Precedent memory: kNN over verified rows (gold labels, accepted predictions, corrections).

Embeddings from Qwen3-Embedding-0.6B; FAISS during the hackathon.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from viveka.context import Context
from viveka.signals import EvidenceCard

DEFAULT_PATH = Path("models/weights/precedents.faiss")


class PrecedentMemory:
    name = "precedents"

    def __init__(self, path: Path = DEFAULT_PATH, k: int = 8):
        self.path = path
        self.k = k

    def available(self) -> bool:
        return self.path.is_file()

    def add(self, rows: Sequence[Mapping[str, object]], labels: Sequence[str]) -> None:
        # TODO(block 3): embed row_text, append to index with label metadata.
        raise NotImplementedError

    def score(
        self,
        cards: Sequence[EvidenceCard],
        rows: Sequence[Mapping[str, object]],
        ctx: Context | None = None,
    ) -> np.ndarray:
        # TODO(block 3): similarity-weighted label vote of the k nearest precedents.
        raise NotImplementedError
