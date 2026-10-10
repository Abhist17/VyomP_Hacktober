"""Labelled examples from (workbook, gold) pairs, through the same front half as inference.

Each example carries the chat messages the SLM will see at inference time, so training and
scoring cannot drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from viveka.context import Context
from viveka.io import read_rows
from viveka.labels import LABELS
from viveka.models.slm import PROMPT_VERSION, build_messages
from viveka.pipeline import prepare
from viveka.signals import EvidenceCard
from viveka.synth import split_files


@dataclass
class Labelled:
    rows: list[dict[str, object]]
    cards: list[EvidenceCard]
    ctx: Context
    labels: list[str]
    gold: pd.DataFrame
    source: Path


def labelled_files(split_dir: str | Path) -> Iterator[Labelled]:
    """Yield each workbook of a split with its gold labels, joined on row order."""
    for book, gold_path in split_files(split_dir):
        rows, cards, ctx, _ = prepare(read_rows(book))
        gold = pd.read_csv(gold_path, dtype=str)
        if len(gold) != len(rows):
            raise ValueError(f"{book}: {len(rows)} rows but {len(gold)} gold labels")
        labels = gold["Voucher Type"].str.strip().tolist()
        unknown = set(labels) - set(LABELS)
        if unknown:
            raise ValueError(f"{gold_path}: unknown labels {sorted(unknown)}")
        yield Labelled(rows, cards, ctx, labels, gold, book)


def export_sft(split_dir: str | Path, out_path: str | Path) -> int:
    """Write one JSON line per row: messages, label, source file and template."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for f in labelled_files(split_dir):
            templates = f.gold["Template"] if "Template" in f.gold else [None] * len(f.rows)
            for row, card, label, tpl in zip(f.rows, f.cards, f.labels, templates, strict=True):
                record = {
                    "messages": build_messages(card, row, f.ctx),
                    "label": label,
                    "source": f.source.name,
                    "template": tpl,
                    "prompt_version": PROMPT_VERSION,
                }
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                n += 1
    return n


def read_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
