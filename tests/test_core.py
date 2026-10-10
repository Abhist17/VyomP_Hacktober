from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from viveka import gstin
from viveka.align import align
from viveka.labels import FLIP, LABELS, flip
from viveka.models.slm import label_gbnf, label_json_schema
from viveka.normalise import code_kind, parse_amount, parse_date


def test_labels_are_the_27_problem_statement_strings():
    assert len(LABELS) == 27
    assert "Purchase Return / Debit Note" in LABELS
    assert "Other / Miscellaneous" in LABELS


def test_flip_is_an_involution_over_nine_pairs():
    assert len(FLIP) == 18
    for label in LABELS:
        assert flip(flip(label)) == label
    assert flip("Contra") == "Contra"


def test_gstin_checksum():
    assert gstin.is_valid("27AAPFU0939F1ZV")
    assert gstin.is_valid(" 27aapfu0939f1zv ")
    assert not gstin.is_valid("27AAPFU0939F1ZW")  # wrong check character
    assert not gstin.is_valid("40AAPFU0939F1ZV")  # no such state code
    assert gstin.pan("27AAPFU0939F1ZV") == "AAPFU0939F"


def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


@given(st.integers(min_value=0, max_value=10**11), st.integers(min_value=0, max_value=99))
def test_indian_amounts_round_trip(rupees, paise):
    text = f"₹{_indian(rupees)}.{paise:02d}"
    assert parse_amount(text) == float(f"{rupees}.{paise:02d}")


def test_amount_formats():
    assert parse_amount("(1,234.50)") == -1234.5
    assert parse_amount("1,234 Dr") == 1234.0
    assert parse_amount("Rs. 500") == 500.0
    assert parse_amount("") is None
    assert parse_amount("n/a") is None
    assert parse_amount("abc") is None


def test_dates():
    assert parse_date("05-09-2026") == date(2026, 9, 5)
    assert parse_date("05/09/2026") == date(2026, 9, 5)
    assert parse_date("2026-09-05") == date(2026, 9, 5)
    assert parse_date("05-Sep-2026") == date(2026, 9, 5)
    assert parse_date(46270) == date(2026, 9, 5)  # Excel serial
    assert parse_date("not a date") is None


def test_hsn_vs_sac():
    assert code_kind("997212") == "SAC"
    assert code_kind("7208") == "HSN"
    assert code_kind(7208.0) == "HSN"
    assert code_kind("") is None


def test_aligner_synonyms_fuzzy_and_unique_claims():
    m = {
        x.header: x
        for x in align(["Inv No", "Pty GSTIN", "Vch Amt", "Narrationn", "Foo Bar", "Total"])
    }
    assert m["Inv No"].field == "invoice_number"
    assert m["Pty GSTIN"].field == "party_gstin"
    assert m["Narrationn"].field == "narration" and m["Narrationn"].stage == "fuzzy"
    assert m["Foo Bar"].field is None
    # "Vch Amt" and "Total" both mean total_amount; only one may claim it.
    claimed = [h for h in ("Vch Amt", "Total") if m[h].field == "total_amount"]
    assert len(claimed) == 1


def test_constrained_output_artefacts_cover_every_label():
    grammar = label_gbnf()
    assert all(f'"{label}"' in grammar for label in LABELS)
    assert label_json_schema()["properties"]["voucher_type"]["enum"] == list(LABELS)
