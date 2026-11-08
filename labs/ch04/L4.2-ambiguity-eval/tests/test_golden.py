"""Golden tests: every number Chapter 4 quotes from Lab 4.2. A change that moves one must fail here."""

import json
import subprocess
import sys

import pytest
from conftest import DATA_DIR, LAB_ROOT

from ambeval import detector, report, scoring
from ambeval.data import DEFECTS, load_lexicon, load_statements

STATEMENTS = load_statements(DATA_DIR / "statements.jsonl")
V1 = load_lexicon(DATA_DIR / "lexicon-v1.json")
V2 = load_lexicon(DATA_DIR / "lexicon-v2.json")


def split(name):
    return [s for s in STATEMENTS if s.split == name]


def test_dataset_shape():
    assert len(STATEMENTS) == 96 and len(split("dev")) == len(split("heldout")) == 48
    assert {s.set for s in split("dev")}.isdisjoint({s.set for s in split("heldout")})
    for name, clean, counts in (("dev", 20, (9, 8, 8, 7)), ("heldout", 22, (7, 12, 8, 8))):
        ss = split(name)
        assert sum(not s.defects for s in ss) == clean
        assert tuple(sum(d in s.defects for s in ss) for d in DEFECTS) == counts


def test_contradictions_come_in_labelled_pairs():
    by_id = {s.id: s for s in STATEMENTS}
    for s in STATEMENTS:
        if "contradiction" in s.defects:
            other = by_id[s.conflicts_with]
            assert other.conflicts_with == s.id and other.set == s.set


def test_v2_adds_four_vague_words_and_one_quality_word():
    assert sorted(set(V2.vague_terms) - set(V1.vague_terms)) == ["large", "several", "soon", "when needed"]
    assert sorted(set(V2.quality_terms) - set(V1.quality_terms)) == ["scale"]


def r(lex, name, defect=None):
    pred = detector.predict(STATEMENTS, lex)
    c = scoring.micro(split(name), pred) if defect is None else scoring.confusion(split(name), pred, defect)
    return c, scoring.rates(c)


def pct(x):
    return round(x * 100)


@pytest.mark.parametrize("lex,name,tp,fp,fn,prec,prec_ci,rec,rec_ci", [
    (V1, "dev", 24, 2, 8, 92, (76, 98), 75, (58, 87)),
    (V2, "dev", 28, 3, 4, 90, (75, 97), 88, (72, 95)),
    (V1, "heldout", 21, 1, 14, 95, (78, 99), 60, (44, 74)),
    (V2, "heldout", 21, 1, 14, 95, (78, 99), 60, (44, 74)),
])
def test_micro_results_quoted_in_chapter_4(lex, name, tp, fp, fn, prec, prec_ci, rec, rec_ci):
    c, rt = r(lex, name)
    assert (c.tp, c.fp, c.fn) == (tp, fp, fn)
    assert pct(rt.precision) == prec and tuple(map(pct, rt.precision_ci)) == prec_ci
    assert pct(rt.recall) == rec and tuple(map(pct, rt.recall_ci)) == rec_ci


@pytest.mark.parametrize("defect,tp,fn,rec,rec_ci", [
    ("ambiguity", 3, 4, 43, (16, 75)),
    ("untestable", 6, 6, 50, (25, 75)),
    ("contradiction", 4, 4, 50, (22, 78)),
    ("missing_actor", 8, 0, 100, (68, 100)),
])
def test_heldout_recall_by_type(defect, tp, fn, rec, rec_ci):
    c, rt = r(V1, "heldout", defect)
    assert (c.tp, c.fn) == (tp, fn)
    assert pct(rt.recall) == rec and tuple(map(pct, rt.recall_ci)) == rec_ci


def test_dev_ambiguity_recall_before_and_after_tuning():
    assert pct(r(V1, "dev", "ambiguity")[1].recall) == 67 and pct(r(V2, "dev", "ambiguity")[1].recall) == 100
    assert pct(r(V2, "heldout", "ambiguity")[1].recall) == 43


def test_the_only_heldout_false_alarm():
    pred = detector.predict(STATEMENTS, V1)
    false = [(s.id, sorted(pred[s.id] - s.defects)) for s in split("heldout") if pred[s.id] - s.defects]
    assert false == [("S060", ["missing_actor"])]


def test_report_prints_the_chapter_rows():
    args = ["--data", str(DATA_DIR / "statements.jsonl"), "--lexicon", str(DATA_DIR / "lexicon-v1.json"),
            "--lexicon", str(DATA_DIR / "lexicon-v2.json")]
    text = report.render_offline(STATEMENTS, [V1, V2], ("dev", "heldout"))
    assert "| detector-lexicon-v1 | heldout | all (micro) | 35 | 21 | 1 | 14 | 95% (78%–99%) | 60% (44%–74%) |" in text
    assert "| detector-lexicon-v2 | dev | all (micro) | 32 | 28 | 3 | 4 | 90% (75%–97%) | 88% (72%–95%) |" in text
    assert report.main(args) == 0


def test_generator_reproduces_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name in ("statements.jsonl", "lexicon-v1.json", "lexicon-v2.json"):
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name
    assert sorted(p.name for p in DATA_DIR.iterdir()) == ["lexicon-v1.json", "lexicon-v2.json", "statements.jsonl"]


@pytest.mark.parametrize("defect,flags,prec_ci", [("ambiguity", 3, (44, 100)), ("untestable", 6, (61, 100))])
def test_heldout_precision_behind_the_warning_policy(defect, flags, prec_ci):
    c, rt = r(V1, "heldout", defect)
    assert (c.tp + c.fp, c.fp) == (flags, 0)
    assert pct(rt.precision) == 100 and tuple(map(pct, rt.precision_ci)) == prec_ci
