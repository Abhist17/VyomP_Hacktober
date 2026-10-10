"""Opinion sources. Each returns a (rows x 27) probability matrix over `viveka.labels.LABELS`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import numpy as np

from viveka.signals import EvidenceCard


class OpinionSource(Protocol):
    name: str

    def available(self) -> bool: ...

    def score(
        self, cards: Sequence[EvidenceCard], rows: Sequence[Mapping[str, object]]
    ) -> np.ndarray: ...
