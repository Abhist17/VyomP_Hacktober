"""Sentinel: LightGBM over evidence-card signals (and later row embeddings).

A fast, independent second opinion with a different inductive bias from the SLM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from viveka.signals import EvidenceCard, registered

DEFAULT_PATH = Path("models/weights/sentinel.txt")


def featurise(cards: Sequence[EvidenceCard]) -> np.ndarray:
    """Three-valued signals as {1, 0, -1}; unknown stays distinguishable from false."""
    names = [name for name, _ in registered()]
    enc = {True: 1.0, False: 0.0, None: -1.0}
    return np.array([[enc[c[n]] for n in names] for c in cards], dtype=np.float32)


class Sentinel:
    name = "sentinel"

    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = path

    def available(self) -> bool:
        return self.path.is_file()

    def fit(self, cards: Sequence[EvidenceCard], labels: Sequence[str]) -> None:
        # TODO(block 3): class-balanced LightGBM multiclass; save to self.path.
        raise NotImplementedError

    def score(
        self, cards: Sequence[EvidenceCard], rows: Sequence[Mapping[str, object]]
    ) -> np.ndarray:
        # TODO(block 3): load booster, predict_proba aligned to LABELS.
        raise NotImplementedError
