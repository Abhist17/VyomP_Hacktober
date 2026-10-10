"""Fuse opinions, calibrate, and attach a prediction set.

Two pooling rules, chosen per policy and tuned on the gold dev split (`viveka tune-fusion`):
`linear` is a weighted mean of the source distributions; `log` is a weighted geometric mean
(product of experts), which lets one confident, well-calibrated source veto the others.

TODO(block 6): replace top-mass sets with split-conformal sets (MAPIE) fitted on gold dev.
"""

from __future__ import annotations

import numpy as np

from viveka.policy import Policy


def pool(
    opinions: dict[str, np.ndarray], weights: dict[str, float], pooling: str = "linear"
) -> np.ndarray:
    """Combine (rows x labels) distributions with per-source weights; zero weight drops one."""
    used = {k: v for k, v in opinions.items() if weights.get(k, 1.0) > 0}
    if not used:
        used = opinions
    total = sum(weights.get(k, 1.0) for k in used) or 1.0
    if pooling == "log":
        logits = sum(weights.get(k, 1.0) * np.log(np.clip(p, 1e-12, 1.0)) for k, p in used.items())
        logits = logits / total
        logits -= logits.max(axis=-1, keepdims=True)
        exp = np.exp(logits)
        return exp / exp.sum(axis=-1, keepdims=True)
    if pooling != "linear":
        raise ValueError(f"Unknown pooling {pooling!r}; use 'linear' or 'log'")
    return sum(weights.get(k, 1.0) * p for k, p in used.items()) / total


def fuse(opinions: dict[str, np.ndarray], policy: Policy) -> np.ndarray:
    weights = {name: policy.weight(name) for name in opinions}
    return temperature_scale(pool(opinions, weights, policy.pooling), policy.temperature)


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
