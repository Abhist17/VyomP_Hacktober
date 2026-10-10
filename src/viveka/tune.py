"""Fit fusion on the gold dev split, then report every configuration on held-out test.

`viveka tune-fusion` scores each opinion source once per split, searches pooling rule and
source weights for dev accuracy (macro-F1 breaks ties), fits a temperature for calibration
and picks the auto-accept threshold that keeps dev precision at or above a target. The
test split is only scored with the choices already made on dev.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from viveka.fusion import pool, temperature_scale
from viveka.guardrails import apply as apply_guardrails
from viveka.io import read_rows
from viveka.labels import LABEL_INDEX, LABELS
from viveka.models import OpinionSource
from viveka.pipeline import prepare
from viveka.policy import Policy
from viveka.signals import EvidenceCard
from viveka.synth import split_files

# Both pooling rules ignore the overall scale of the weights, so the largest weight is 1.
WEIGHT_GRID = (0.0, 0.25, 0.5, 1.0)
TEMPERATURES = (0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0, 3.0)


@dataclass
class Scored:
    """Every source's opinions on one labelled split, row-aligned with gold and cards."""

    opinions: dict[str, np.ndarray]
    gold: np.ndarray
    cards: list[EvidenceCard]
    heldout: np.ndarray

    def save(self, path: str | Path) -> None:
        np.savez(
            path,
            gold=self.gold,
            heldout=self.heldout,
            **{f"op_{k}": v for k, v in self.opinions.items()},
        )


def collect(split_dir: str | Path, sources: Sequence[OpinionSource]) -> Scored:
    opinions: dict[str, list[np.ndarray]] = {s.name: [] for s in sources}
    gold: list[str] = []
    heldout: list[bool] = []
    cards: list[EvidenceCard] = []
    for book, labels in split_files(split_dir):
        g = pd.read_csv(labels, dtype=str)
        rows, book_cards, ctx, _ = prepare(read_rows(book))
        if len(rows) != len(g):
            raise ValueError(f"{book}: {len(rows)} rows but {len(g)} gold labels")
        for s in sources:
            opinions[s.name].append(s.score(book_cards, rows, ctx))
        gold += list(g["Voucher Type"])
        flags = g["Heldout"].str.lower() == "true" if "Heldout" in g else [False] * len(g)
        heldout += list(flags)
        cards += book_cards
    return Scored(
        {k: np.vstack(v) for k, v in opinions.items()},
        np.array(gold),
        cards,
        np.array(heldout, dtype=bool),
    )


def decide(probs: np.ndarray, cards: Sequence[EvidenceCard]) -> np.ndarray:
    """Apply the accounting guardrails row by row, exactly as the pipeline does."""
    return np.vstack([apply_guardrails(p, c)[0] for p, c in zip(probs, cards, strict=True)])


def scores(
    probs: np.ndarray, gold: np.ndarray, coverage: float, threshold: float
) -> dict[str, float | None]:
    pred = np.array(LABELS)[probs.argmax(axis=1)]
    correct = pred == gold
    conf = probs.max(axis=1)
    # Mirrors pipeline.needs_review: singleton prediction set and confidence over threshold.
    auto = (conf >= coverage) & (conf >= threshold)
    return {
        "accuracy": float(correct.mean()),
        "macro_f1": float(f1_score(gold, pred, average="macro", zero_division=0)),
        "auto_accept_coverage": float(auto.mean()),
        "auto_accept_precision": float(correct[auto].mean()) if auto.any() else None,
        "nll": float(
            -np.log(np.clip(probs[np.arange(len(gold)), _gold_idx(gold)], 1e-12, 1)).mean()
        ),
    }


def _gold_idx(gold: np.ndarray) -> np.ndarray:
    return np.array([LABEL_INDEX[g] for g in gold])


@dataclass
class Choice:
    pooling: str
    weights: dict[str, float]
    temperature: float = 1.0
    threshold: float = 0.90
    coverage: float = 0.95

    def apply(self, scored: Scored) -> np.ndarray:
        probs = pool(scored.opinions, self.weights, self.pooling)
        return decide(temperature_scale(probs, self.temperature), scored.cards)


def search(dev: Scored) -> list[tuple[float, float, Choice]]:
    """Every pooling x weight combination, ranked by dev accuracy then macro-F1."""
    names = sorted(dev.opinions)
    ranked = []
    for pooling in ("linear", "log"):
        for combo in itertools.product(WEIGHT_GRID, repeat=len(names)):
            if max(combo) != 1.0:
                continue
            choice = Choice(pooling, dict(zip(names, combo, strict=True)))
            probs = choice.apply(dev)
            pred = np.array(LABELS)[probs.argmax(axis=1)]
            acc = float((pred == dev.gold).mean())
            f1 = float(f1_score(dev.gold, pred, average="macro", zero_division=0))
            ranked.append((acc, f1, choice))
    # Prefer fewer active sources and smaller total weight on ties: simpler, cheaper.
    ranked.sort(
        key=lambda r: (
            -r[0],
            -r[1],
            sum(w > 0 for w in r[2].weights.values()),
            sum(r[2].weights.values()),
        )
    )
    return ranked


def fit_temperature(dev: Scored, choice: Choice) -> float:
    idx = _gold_idx(dev.gold)
    base = pool(dev.opinions, choice.weights, choice.pooling)
    best, best_nll = 1.0, float("inf")
    for t in TEMPERATURES:
        probs = decide(temperature_scale(base, t), dev.cards)
        nll = float(-np.log(np.clip(probs[np.arange(len(idx)), idx], 1e-12, 1)).mean())
        if nll < best_nll:
            best, best_nll = t, nll
    return best


def fit_threshold(dev: Scored, choice: Choice, target: float) -> float:
    """Lowest auto-accept cut-off whose dev precision stays at or above `target`.

    Used as both the confidence threshold and the prediction-set coverage, so a row is
    auto-accepted exactly when one label alone carries at least that much probability.
    """
    probs = choice.apply(dev)
    conf = probs.max(axis=1)
    correct = np.array(LABELS)[probs.argmax(axis=1)] == dev.gold
    for t in np.round(np.arange(0.50, 0.995, 0.01), 2):
        auto = conf >= t
        if auto.any() and correct[auto].mean() >= target:
            return float(t)
    return 0.99


def tune(dev: Scored, test: Scored | None, policy: Policy, target_precision: float = 0.995) -> dict:
    ranked = search(dev)
    best = ranked[0][2]
    best.temperature = fit_temperature(dev, best)
    best.threshold = best.coverage = fit_threshold(dev, best, target_precision)

    def report(choice: Choice, name: str, description: str) -> dict:
        out = {"name": name, "description": description, "pooling": choice.pooling}
        out["weights"] = choice.weights
        out["temperature"] = choice.temperature
        out["threshold"] = choice.threshold
        out["coverage"] = choice.coverage
        out["dev"] = scores(choice.apply(dev), dev.gold, choice.coverage, choice.threshold)
        if test is not None:
            probs = choice.apply(test)
            out["test"] = scores(probs, test.gold, choice.coverage, choice.threshold)
            pred = np.array(LABELS)[probs.argmax(axis=1)]
            correct = pred == test.gold
            if test.heldout.any():
                out["test"]["accuracy_heldout_templates"] = float(correct[test.heldout].mean())
                out["test"]["accuracy_seen_templates"] = float(correct[~test.heldout].mean())
        return out

    names = sorted(dev.opinions)
    only = {n: {m: float(m == n) for m in names} for n in names}
    current = {n: policy.weight(n) for n in names}
    before = (policy.auto_accept_threshold, policy.coverage)
    configs = [report(Choice("linear", only[n], 1.0, *before), n, n) for n in names]
    configs.append(
        report(
            Choice(policy.pooling, current, policy.temperature, *before),
            "fused-before",
            "fused (hand-set weights)",
        )
    )
    configs.append(report(best, "fused-tuned", "fused (tuned on dev)"))
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "policy_version": policy.version,
        "target_precision": target_precision,
        "chosen": {
            "pooling": best.pooling,
            "weights": best.weights,
            "temperature": best.temperature,
            "auto_accept_threshold": best.threshold,
            "coverage": best.coverage,
        },
        "top_dev_candidates": [
            {"accuracy": a, "macro_f1": f, "pooling": c.pooling, "weights": c.weights}
            for a, f, c in ranked[:10]
        ],
        "configs": configs,
    }


def evaluation_card(report: Mapping, split: str, rows: int, labels: Mapping[str, str]) -> dict:
    """Compact, test-only summary served by `/v1/model-card` and shown in the web app."""
    return {
        "split": split,
        "rows": rows,
        "selected": "fused-tuned",
        "created_at": report["created_at"],
        "results": [
            {
                "name": c["name"],
                "description": labels.get(c["name"], c["description"]),
                "accuracy": c["test"]["accuracy"],
                "macro_f1": c["test"]["macro_f1"],
                "auto_accept_precision": c["test"]["auto_accept_precision"],
                "auto_accept_coverage": c["test"]["auto_accept_coverage"],
            }
            for c in report["configs"]
            if "test" in c
        ],
    }


def write_policy(path: str | Path, chosen: Mapping) -> None:
    """Rewrite the [decision] and [opinions] values in place, keeping comments and layout."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    updates = {
        ("decision", "auto_accept_threshold"): f"{chosen['auto_accept_threshold']:.2f}",
        ("decision", "temperature"): f"{chosen['temperature']}",
        ("decision", "coverage"): f"{chosen['coverage']:.2f}",
        ("decision", "pooling"): json.dumps(chosen["pooling"]),
        **{("opinions", k): f"{v}" for k, v in chosen["weights"].items()},
    }
    section, seen, out = "", set(), []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            # New keys go after the section's last value, before its trailing blank lines.
            blanks = 0
            while out and not out[-1].strip():
                out.pop()
                blanks += 1
            out += _missing(section, updates, seen) + [""] * blanks
            section = stripped.strip("[]")
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
        if key and (section, key) in updates and not stripped.startswith("#"):
            comment = line.split("#", 1)[1] if "#" in line.split("=", 1)[1] else ""
            line = f"{key} = {updates[(section, key)]}" + (
                f"  # {comment.strip()}" if comment else ""
            )
            seen.add((section, key))
        out.append(line)
    out += _missing(section, updates, seen)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _missing(section: str, updates: Mapping, seen: set) -> list[str]:
    new = [f"{k} = {v}" for (s, k), v in updates.items() if s == section and (s, k) not in seen]
    seen.update((section, k) for (s, k) in updates if s == section)
    return new
