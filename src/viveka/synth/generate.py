"""Build the synthetic train / dev / test splits.

- train and dev: the same 8 companies ("seen" name pool), seen templates, seen dialects.
- test: 4 new companies from a disjoint name pool, half the rows from templates that never
  appear in train, and half the files in a header dialect never seen in train.

Every split is balanced over the 27 labels so macro-F1 is meaningful. Output is a pure
function of the seed.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from viveka.labels import LABELS
from viveka.synth.events import TEMPLATES, Template
from viveka.synth.render import (
    SEEN_DIALECTS,
    UNSEEN_DIALECT,
    Dialect,
    add_noise,
    write_book,
    write_gold,
)
from viveka.synth.world import Company, Names, make_company

START = date(2026, 4, 1)
DAYS = 183


@dataclass(frozen=True)
class FileSpec:
    split: str
    company: Company
    dialect: Dialect
    rows: int
    heldout_share: float


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _balanced_labels(n: int, rng: random.Random) -> list[str]:
    labels = (list(LABELS) * (n // len(LABELS) + 1))[:n]
    rng.shuffle(labels)
    return labels


def _choose_template(label: str, heldout_share: float, rng: random.Random) -> Template:
    seen = [t for t in TEMPLATES[label] if not t.heldout]
    held = [t for t in TEMPLATES[label] if t.heldout]
    if held and rng.random() < heldout_share:
        return rng.choice(held)
    return rng.choice(seen)


def build_file(spec: FileSpec, out_dir: Path, rng: random.Random) -> dict[str, object]:
    c = spec.company
    events = []
    used: set[str] = set()
    for label in _balanced_labels(spec.rows, rng):
        tpl = _choose_template(label, spec.heldout_share, rng)
        d = START + timedelta(days=rng.randrange(DAYS))
        row = tpl.fn(c, rng, d)
        number, suffix = str(row["invoice_number"]), 2
        while number in used:
            number = f"{row['invoice_number']}-{suffix}"
            suffix += 1
        used.add(number)
        row["invoice_number"] = number
        when = row.get("invoice_date") or d
        row = add_noise(row, label, tpl.core, c, spec.dialect, rng)
        events.append((when, row, label, tpl))
    events.sort(key=lambda e: e[0])

    stem = _slug(c.name)
    book = out_dir / spec.split / f"{stem}.xlsx"
    title = f"Day Book: 1-Apr-2026 to 30-Sep-2026 ({spec.dialect.name})"
    write_book(book, [e[1] for e in events], c, spec.dialect, title)
    write_gold(
        out_dir / spec.split / f"{stem}.gold.csv",
        [
            {
                "Invoice No": row["invoice_number"],
                "Voucher Type": label,
                "Template": tpl.name,
                "Heldout": tpl.heldout,
                "Company": c.name,
            }
            for _, row, label, tpl in events
        ],
    )
    return {
        "file": str(book.relative_to(out_dir)),
        "company": c.name,
        "company_gstin": c.gstin,
        "dialect": spec.dialect.name,
        "rows": len(events),
        "heldout_rows": sum(e[3].heldout for e in events),
    }


def generate(
    out_dir: str | Path,
    seed: int = 7,
    n_train: int = 3000,
    n_dev: int = 600,
    n_test: int = 800,
    seen_companies: int = 8,
    unseen_companies: int = 4,
    heldout_share: float = 0.5,
) -> dict[str, object]:
    out_dir = Path(out_dir)
    rng = random.Random(seed)
    seen_names = Names("seen", random.Random(seed + 1))
    unseen_names = Names("unseen", random.Random(seed + 2))
    seen = [make_company("seen", rng, seen_names) for _ in range(seen_companies)]
    unseen = [make_company("unseen", rng, unseen_names) for _ in range(unseen_companies)]

    specs: list[FileSpec] = []
    n_dialects = len(SEEN_DIALECTS)
    for i, c in enumerate(seen):
        specs.append(FileSpec("train", c, SEEN_DIALECTS[i % n_dialects], n_train // len(seen), 0))
        specs.append(FileSpec("dev", c, SEEN_DIALECTS[(i + 1) % n_dialects], n_dev // len(seen), 0))
    for i, c in enumerate(unseen):
        dialect = UNSEEN_DIALECT if i % 2 == 0 else SEEN_DIALECTS[i % n_dialects]
        specs.append(FileSpec("test", c, dialect, n_test // len(unseen), heldout_share))

    files = [
        build_file(s, out_dir, random.Random(f"{seed}:{s.split}:{s.company.name}")) for s in specs
    ]
    manifest = {
        "seed": seed,
        "splits": {
            split: [f for f, s in zip(files, specs, strict=True) if s.split == split]
            for split in ("train", "dev", "test")
        },
        "heldout_templates": sorted(
            f"{t.label}: {t.name}" for ts in TEMPLATES.values() for t in ts if t.heldout
        ),
        "unseen_dialect": UNSEEN_DIALECT.name,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def split_files(split_dir: str | Path) -> list[tuple[Path, Path]]:
    """(workbook, gold) pairs in a split directory."""
    split_dir = Path(split_dir)
    pairs = []
    for book in sorted(split_dir.glob("*.xlsx")):
        gold = book.with_name(book.stem + ".gold.csv")
        if gold.is_file():
            pairs.append((book, gold))
    if not pairs:
        raise FileNotFoundError(f"No <name>.xlsx + <name>.gold.csv pairs in {split_dir}")
    return pairs
