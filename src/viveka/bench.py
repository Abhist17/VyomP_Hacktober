"""Benchmark: every opinion source alone and fused, on a labelled split (`viveka bench`).

Reports accuracy, macro-F1, the confusable-pair scoreboard, accuracy on held-out templates
versus seen ones, and throughput, so "the fine-tuned SLM beats zero-shot and rules" is a
measured claim rather than a preference (README section 9, decision rules).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from viveka import __version__
from viveka.evaluate import label_metrics
from viveka.io import read_rows
from viveka.models import OpinionSource
from viveka.models.rules import RulesOpinion
from viveka.models.sentinel import DEFAULT_PATH as SENTINEL_PATH
from viveka.models.sentinel import Sentinel
from viveka.models.slm import SLMAdjudicator
from viveka.pipeline import run
from viveka.policy import Policy
from viveka.synth import split_files


@dataclass
class Config:
    name: str
    sources: Callable[[], list[OpinionSource]]
    mode: str = "accurate"


def configs(policy: Policy) -> list[Config]:
    rules = RulesOpinion(policy)
    sentinel = Sentinel(
        policy.sentinel.get("path", SENTINEL_PATH), policy.sentinel.get("embedder", "tfidf")
    )
    tuned = SLMAdjudicator(policy.slm)
    zero = SLMAdjudicator({**policy.slm, "adapter": ""})
    best = tuned if tuned.adapter_path else zero
    return [
        Config("rules", lambda: [rules]),
        Config("sentinel", lambda: [sentinel]),
        Config("slm-zero-shot", lambda: [zero]),
        Config("slm-fine-tuned", lambda: [tuned] if tuned.adapter_path else []),
        Config("rules+sentinel", lambda: [rules, sentinel]),
        Config("fused", lambda: [rules, sentinel, best]),
        Config("fused-fast", lambda: [rules, sentinel, best], mode="fast"),
    ]


def _share(mask: np.ndarray, correct: np.ndarray) -> float | None:
    return float(correct[mask].mean()) if mask.any() else None


def bench(
    split_dir: str | Path,
    policy: Policy,
    only: list[str] | None = None,
    limit_files: int | None = None,
) -> dict:
    pairs = split_files(split_dir)[:limit_files]
    books = [(read_rows(b), pd.read_csv(g, dtype=str)) for b, g in pairs]
    gold = pd.concat([g for _, g in books], ignore_index=True)
    if "Heldout" in gold:
        heldout = (gold["Heldout"].str.lower() == "true").to_numpy()
    else:
        heldout = np.zeros(len(gold), dtype=bool)

    results: dict[str, dict] = {}
    for cfg in configs(policy):
        if only and cfg.name not in only:
            continue
        sources = [s for s in cfg.sources() if s.available()]
        if not sources:
            results[cfg.name] = {"skipped": "source not available"}
            continue
        preds, slm_rows = [], 0
        started = time.perf_counter()
        for raw, _ in books:
            r = run(raw, policy, mode=cfg.mode, sources=sources)
            preds += [p.voucher_type for p in r.predictions]
            slm_rows += sum("slm" in p.decided_by.split("+") for p in r.predictions)
        seconds = time.perf_counter() - started
        m = label_metrics(gold["Voucher Type"], pd.Series(preds))
        correct = gold["Voucher Type"].to_numpy() == np.array(preds)
        present = set(m["confusion_matrix"]["labels"])
        results[cfg.name] = {
            "sources": [getattr(s, "version", s.name) for s in sources],
            "mode": cfg.mode,
            "rows": len(gold),
            "accuracy": m["accuracy"],
            "macro_f1": m["macro_f1"],
            "macro_precision": m["per_class"]["macro avg"]["precision"],
            "macro_recall": m["per_class"]["macro avg"]["recall"],
            "accuracy_seen_templates": _share(~heldout, correct),
            "accuracy_heldout_templates": _share(heldout, correct),
            "confusable_pairs": m["confusable_pairs"],
            "per_class": {
                k: {"precision": v["precision"], "recall": v["recall"], "f1": v["f1-score"]}
                for k, v in m["per_class"].items()
                if k in present
            },
            "per_class_f1": {k: v["f1-score"] for k, v in m["per_class"].items() if k in present},
            "seconds": round(seconds, 2),
            "rows_per_second": round(len(gold) / seconds, 2) if seconds else None,
            "slm_rows": slm_rows,
        }
    return {
        "viveka_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "split": str(split_dir),
        "files": [str(b) for b, _ in pairs],
        "policy_version": policy.version,
        "results": results,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:.1f}%"


def write_bench(report: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bench.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Viveka benchmark",
        "",
        f"Split `{report['split']}`, {len(report['files'])} files, policy "
        f"`{report['policy_version']}`, {report['created_at']}.",
        "",
        "| Config | Accuracy | Macro-F1 | Macro-P | Macro-R | Seen templates "
        "| Held-out templates | Rows/s | SLM rows |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    ok = {k: v for k, v in report["results"].items() if "skipped" not in v}
    for name, r in report["results"].items():
        if "skipped" in r:
            lines.append(f"| {name} | skipped: {r['skipped']} | | | | | | | |")
            continue
        lines.append(
            f"| {name} | {_pct(r['accuracy'])} | {_pct(r['macro_f1'])} | "
            f"{_pct(r.get('macro_precision'))} | {_pct(r.get('macro_recall'))} | "
            f"{_pct(r['accuracy_seen_templates'])} | {_pct(r['accuracy_heldout_templates'])} | "
            f"{r['rows_per_second']} | {r['slm_rows']} |"
        )
    if ok:
        pair_names = list(next(iter(ok.values()))["confusable_pairs"])
        lines += ["", "## Confusable pairs (error rate)", ""]
        lines.append("| Pair | " + " | ".join(ok) + " |")
        lines.append("|---|" + "---|" * len(ok))
        for pair in pair_names:
            cells = [_pct(r["confusable_pairs"][pair]["error_rate"]) for r in ok.values()]
            lines.append(f"| {pair} | " + " | ".join(cells) + " |")
    path = out_dir / "bench.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
