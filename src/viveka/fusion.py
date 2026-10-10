"""Fuse opinions, calibrate, and attach a prediction set.

TODO(block 3): replace the weighted mean with a stacking model fitted on the gold dev split.
TODO(block 6): replace top-mass sets with split-conformal sets (MAPIE) fitted on gold dev.
"""

from __future__ import annotations

import numpy as np

from viveka.policy import Policy


def fuse(opinions: dict[str, np.ndarray], policy: Policy) -> np.ndarray:
    total = sum(policy.weight(name) * p for name, p in opinions.items())
    weight = sum(policy.weight(name) for name in opinions)
    return temperature_scale(total / weight, policy.temperature)


def temperature_scale(probs: np.ndarray, temperature: float) -> np.ndarray:
    if temperature == 1.0:
        return probs
    logits = np.log(np.clip(probs, 1e-12, 1.0)) / temperature
    logits -= logits.max(axis=-1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=-1, keepdims=True)


def prediction_set(probs: np.ndarray, coverage: float) -> list[int]:
    """Smallest set of labels whose probability mass reaches `coverage`."""
    order = np.argsort(-probs)
    cumulative = np.cumsum(probs[order])
    k = int(np.searchsorted(cumulative, coverage) + 1)
    return [int(i) for i in order[: min(k, len(order))]]
