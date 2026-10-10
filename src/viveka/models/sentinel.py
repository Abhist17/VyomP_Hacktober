"""Sentinel: a fast classifier over row text and evidence-card signals.

A second opinion with a different inductive bias from the SLM. Text is embedded either with
TF-IDF word and character n-grams (default, no download, milliseconds per row) or with an
open embedding model through sentence-transformers (e.g. Qwen/Qwen3-Embedding-0.6B). The
three-valued signals are appended, and a class-balanced logistic regression gives
probabilities over the 27 labels.

The bundle is a joblib pickle written by `viveka train-sentinel`; load only bundles you
trained yourself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from viveka.context import Context
from viveka.labels import LABEL_INDEX, LABELS
from viveka.signals import EvidenceCard, registered

DEFAULT_PATH = Path("models/weights/sentinel.joblib")
BUNDLE_VERSION = 1


def featurise(cards: Sequence[EvidenceCard]) -> np.ndarray:
    """Three-valued signals as {1, 0, -1}; unknown stays distinguishable from false."""
    names = [name for name, _ in registered()]
    enc = {True: 1.0, False: 0.0, None: -1.0}
    return np.array([[enc[c[n]] for n in names] for c in cards], dtype=np.float32)


def sentinel_text(row: Mapping[str, object], card: EvidenceCard) -> str:
    """Field names plus values; the company's role is spelled out so text carries direction."""
    from viveka.models.slm import row_text

    role = [s for s in ("company_is_seller", "company_is_buyer") if card[s]]
    return " ".join(role) + "\n" + row_text(row)


class Embedder:
    """TF-IDF (fitted here) or a sentence-transformers model (loaded on first use)."""

    def __init__(self, kind: str = "tfidf"):
        self.kind = kind
        self.vectorizer: Any = None
        self._st: Any = None

    def fit(self, texts: list[str]) -> None:
        if self.kind != "tfidf":
            return
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import FeatureUnion

        self.vectorizer = FeatureUnion(
            [
                ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                (
                    "char",
                    TfidfVectorizer(
                        analyzer="char_wb",
                        ngram_range=(3, 5),
                        min_df=3,
                        sublinear_tf=True,
                        max_features=60000,
                    ),
                ),
            ]
        )
        self.vectorizer.fit(texts)

    def transform(self, texts: list[str]):
        if self.kind == "tfidf":
            return self.vectorizer.transform(texts)
        if self._st is None:
            from sentence_transformers import SentenceTransformer

            self._st = SentenceTransformer(self.kind)
        return self._st.encode(texts, normalize_embeddings=True, batch_size=32)

    def __getstate__(self) -> dict[str, Any]:
        return {"kind": self.kind, "vectorizer": self.vectorizer, "_st": None}


def _stack(text_features, signals: np.ndarray):
    from scipy import sparse

    if sparse.issparse(text_features):
        return sparse.hstack([text_features, sparse.csr_matrix(signals)]).tocsr()
    return np.hstack([text_features, signals])


class Sentinel:
    name = "sentinel"

    def __init__(self, path: Path | str = DEFAULT_PATH, embedder: str = "tfidf"):
        self.path = Path(path)
        self.embedder = embedder
        self._bundle: dict[str, Any] | None = None

    def available(self) -> bool:
        return self.path.is_file()

    def fit(
        self,
        cards: Sequence[EvidenceCard],
        rows: Sequence[Mapping[str, object]],
        labels: Sequence[str],
        c: float = 4.0,
    ) -> None:
        from sklearn.linear_model import LogisticRegression

        unknown = set(labels) - set(LABELS)
        if unknown:
            raise ValueError(f"Unknown labels: {sorted(unknown)}")
        texts = [sentinel_text(r, card) for r, card in zip(rows, cards, strict=True)]
        emb = Embedder(self.embedder)
        emb.fit(texts)
        x = _stack(emb.transform(texts), featurise(cards))
        clf = LogisticRegression(C=c, max_iter=3000, class_weight="balanced")
        clf.fit(x, list(labels))
        self._bundle = {
            "version": BUNDLE_VERSION,
            "embedder": emb,
            "clf": clf,
            "signals": [name for name, _ in registered()],
        }

    def save(self) -> Path:
        import joblib

        if self._bundle is None:
            raise RuntimeError("fit() before save()")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._bundle, self.path)
        return self.path

    def _load(self) -> dict[str, Any]:
        if self._bundle is None:
            import joblib

            bundle = joblib.load(self.path)
            if bundle.get("signals") != [name for name, _ in registered()]:
                raise ValueError(f"{self.path} was trained on a different signal set; retrain")
            self._bundle = bundle
        return self._bundle

    def score(
        self,
        cards: Sequence[EvidenceCard],
        rows: Sequence[Mapping[str, object]],
        ctx: Context | None = None,
    ) -> np.ndarray:
        if not cards:
            return np.zeros((0, len(LABELS)))
        bundle = self._load()
        texts = [sentinel_text(r, card) for r, card in zip(rows, cards, strict=True)]
        x = _stack(bundle["embedder"].transform(texts), featurise(cards))
        proba = bundle["clf"].predict_proba(x)
        out = np.full((len(cards), len(LABELS)), 1e-4)
        for j, label in enumerate(bundle["clf"].classes_):
            out[:, LABEL_INDEX[label]] += proba[:, j]
        return out / out.sum(axis=1, keepdims=True)
