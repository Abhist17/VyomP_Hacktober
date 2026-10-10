import numpy as np

from viveka.fusion import pool
from viveka.labels import LABEL_INDEX, LABELS
from viveka.signals import EvidenceCard
from viveka.tune import Choice, Scored, fit_threshold, search, write_policy


def _onehot(labels, strength=0.9):
    out = np.full((len(labels), len(LABELS)), (1 - strength) / (len(LABELS) - 1))
    for i, label in enumerate(labels):
        out[i, LABEL_INDEX[label]] = strength
    return out


def test_log_pooling_lets_a_confident_source_win():
    sure = _onehot(["Sales"], 0.99)
    unsure = _onehot(["Purchase"], 0.30)
    linear = pool({"a": sure, "b": unsure}, {"a": 1, "b": 1}, "linear")
    log = pool({"a": sure, "b": unsure}, {"a": 1, "b": 1}, "log")
    assert LABELS[linear.argmax()] == "Sales"
    assert LABELS[log.argmax()] == "Sales"
    assert np.isclose(log.sum(), 1.0)
    # A zero weight removes a source entirely.
    only_b = pool({"a": sure, "b": unsure}, {"a": 0, "b": 1}, "linear")
    assert LABELS[only_b.argmax()] == "Purchase"


def test_search_prefers_the_accurate_source():
    gold = np.array(["Sales", "Purchase", "Contra", "Journal"] * 5)
    good = _onehot(list(gold), 0.8)
    bad = _onehot(["Sales"] * len(gold), 0.95)
    cards = [EvidenceCard(row_id=i) for i in range(len(gold))]
    dev = Scored({"good": good, "bad": bad}, gold, cards, np.zeros(len(gold), dtype=bool))
    acc, _, best = search(dev)[0]
    assert acc == 1.0
    assert best.weights["good"] > best.weights["bad"]
    threshold = fit_threshold(dev, best, target=0.98)
    assert 0.5 <= threshold <= 0.99


def test_write_policy_updates_values_and_keeps_comments(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text(
        'version = "x"\n\n[decision]\nauto_accept_threshold = 0.90  # tune me\n'
        "temperature = 1.0\n\n[opinions]\nrules = 1.0\nslm = 2.0\n",
        encoding="utf-8",
    )
    write_policy(
        path,
        {
            "auto_accept_threshold": 0.83,
            "temperature": 0.5,
            "coverage": 0.83,
            "pooling": "log",
            "weights": {"rules": 0.25, "slm": 1.0, "sentinel": 0.5},
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "auto_accept_threshold = 0.83  # tune me" in text
    assert 'pooling = "log"' in text
    assert "rules = 0.25" in text and "sentinel = 0.5" in text

    import tomllib

    data = tomllib.loads(text)
    assert data["decision"]["temperature"] == 0.5
    assert data["opinions"]["slm"] == 1.0
    assert Choice("log", data["opinions"]).pooling == "log"
