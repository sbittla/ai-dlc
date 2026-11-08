"""The versioned dataset: pinning, splits, slices and leakage checks."""

import shutil
import subprocess
import sys

import pytest
from conftest import DATA_DIR, LAB_ROOT

from evalsuite import dataset

TICKETS = dataset.load_tickets(DATA_DIR / "tickets.jsonl")


def test_dataset_shape():
    assert len(TICKETS) == 300
    assert len(dataset.split(TICKETS, "dev")) == 100
    assert len(dataset.split(TICKETS, "heldout")) == 200
    assert sum(t["source"] == "chapter-2" and t["split"] == "dev" for t in TICKETS) == 40


def test_no_family_crosses_the_split():
    dev = {t["family"] for t in TICKETS if t["split"] == "dev"}
    held = {t["family"] for t in TICKETS if t["split"] == "heldout"}
    assert not dev & held


def test_pin_matches_and_detects_tampering(tmp_path):
    assert dataset.verify_pin(DATA_DIR, "relay-triage-eval", "2026.11.1").ok
    assert not dataset.verify_pin(DATA_DIR, "relay-triage-eval", "2026.10.0").ok
    shutil.copy(DATA_DIR / "manifest.json", tmp_path / "manifest.json")
    text = (DATA_DIR / "tickets.jsonl").read_text(encoding="utf-8")
    (tmp_path / "tickets.jsonl").write_text(text.replace('"P4"', '"P3"', 1), encoding="utf-8")
    pin = dataset.verify_pin(tmp_path, "relay-triage-eval", "2026.11.1")
    assert not pin.ok and "hash" in pin.detail


def test_hash_ignores_line_endings(tmp_path):
    text = (DATA_DIR / "tickets.jsonl").read_text(encoding="utf-8")
    (tmp_path / "crlf.jsonl").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert dataset.canonical_sha256(tmp_path / "crlf.jsonl") == dataset.canonical_sha256(DATA_DIR / "tickets.jsonl")


def test_generator_reproduces_the_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name in ("tickets.jsonl", "manifest.json", "agent-tasks.jsonl"):
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name


def test_slices_of():
    t = {"kind": "overstated", "language": "de", "source": "production", "difficulty": "hard"}
    assert dataset.slices_of(t) == ["kind:overstated", "language:de", "source:production", "difficulty:hard"]


# ------------------------------------------------------------ leakage fixtures

def T(tid, family, text):
    return {"id": tid, "family": family, "text": text}


def test_containment_by_hand():
    # "how do i rename a project" has 4 word 3-grams; the prompt contains 2 of them.
    assert dataset.containment("How do I rename a project?", "Ask: how do I rename things") == pytest.approx(0.5)
    assert dataset.containment("", "anything") == 0.0


def test_check_leakage_finds_all_three_kinds():
    dev = [T("D1", "F1", "The export button does nothing in Firefox."),
           T("D2", "F2", "How do I add a guest to a project?")]
    held = [T("H1", "F3", "Webhooks are degraded since yesterday and we are missing events."),
            T("H2", "F2", "hi, how do i add a guest to a project"),
            T("H3", "F4", "Please add a dark theme to the board.")]
    prompt = "Examples: <ticket>Webhooks are degraded since yesterday and we are missing events.</ticket>"
    leak = dataset.check_leakage(prompt, dev, held, threshold=0.5)
    assert leak.family_overlap == ["F2"]
    assert leak.prompt_hits == [("H1", 1.0)]
    assert leak.cross_split == [("H2", "D2", 0.88)]   # 7 of its 8 word 3-grams are in D2
    assert not leak.clean


def test_check_leakage_clean_case():
    dev = [T("D1", "F1", "The export button does nothing in Firefox.")]
    held = [T("H1", "F2", "Please add a dark theme to the board.")]
    leak = dataset.check_leakage("You triage support tickets.", dev, held)
    assert leak.clean and leak.prompt_hits == [] and leak.cross_split == [] and leak.family_overlap == []
