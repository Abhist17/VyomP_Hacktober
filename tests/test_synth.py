import hashlib

import numpy as np
import pandas as pd
import pytest

from viveka.align import align
from viveka.io import read_rows
from viveka.labels import LABELS
from viveka.models.sentinel import Sentinel
from viveka.synth import generate, split_files
from viveka.train.sft import labelled_files

# Distractor columns the generator adds on purpose; everything else must align.
DISTRACTORS = {"Shift", "Leave Type", "Variance"}
PROVENANCE = {"_row_id", "_sheet"}


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    out = tmp_path_factory.mktemp("synth")
    manifest = generate(out, seed=7, n_train=432, n_dev=216, n_test=216)
    return out, manifest


def _gold_digest(out) -> str:
    h = hashlib.sha256()
    for split in ("train", "dev", "test"):
        for _, gold in split_files(out / split):
            h.update(gold.read_bytes())
    return h.hexdigest()


def test_same_seed_gives_identical_gold(books, tmp_path):
    out, manifest = books
    again = generate(tmp_path, seed=7, n_train=432, n_dev=216, n_test=216)
    for split in ("train", "dev", "test"):
        a = [(f["company"], f["rows"], f["heldout_rows"]) for f in again["splits"][split]]
        b = [(f["company"], f["rows"], f["heldout_rows"]) for f in manifest["splits"][split]]
        assert a == b
    assert _gold_digest(tmp_path) == _gold_digest(out)


def test_every_split_has_all_27_labels(books):
    out, _ = books
    for split in ("train", "dev", "test"):
        labels = set()
        for _, gold in split_files(out / split):
            labels |= set(pd.read_csv(gold, dtype=str)["Voucher Type"])
        assert labels == set(LABELS), split


def test_test_companies_are_disjoint_from_train(books):
    _, manifest = books
    train = {f["company"] for f in manifest["splits"]["train"]}
    test = {f["company"] for f in manifest["splits"]["test"]}
    assert train and test and not train & test
    assert sum(f["heldout_rows"] for f in manifest["splits"]["test"]) > 0
    assert sum(f["heldout_rows"] for f in manifest["splits"]["train"]) == 0


def test_every_header_aligns_except_distractors(books):
    out, _ = books
    for split in ("train", "dev", "test"):
        for book, _ in split_files(out / split):
            unmapped = {m.header for m in align(list(read_rows(book).columns)) if m.field is None}
            assert unmapped <= DISTRACTORS | PROVENANCE, (book.name, unmapped)


def test_sentinel_fit_save_load_score(books, tmp_path):
    out, _ = books
    cards, rows, labels = [], [], []
    for f in labelled_files(out / "train"):
        cards += f.cards
        rows += f.rows
        labels += f.labels
    path = tmp_path / "sentinel.joblib"
    fitted = Sentinel(path)
    fitted.fit(cards, rows, labels)
    fitted.save()

    loaded = Sentinel(path)
    assert loaded.available()
    probs = loaded.score(cards[:50], rows[:50])
    assert probs.shape == (50, len(LABELS))
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert np.allclose(probs, fitted.score(cards[:50], rows[:50]))
    assert loaded.score([], []).shape == (0, len(LABELS))
