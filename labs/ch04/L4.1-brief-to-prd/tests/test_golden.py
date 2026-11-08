"""Golden tests: every number Chapter 4 quotes from Lab 4.1. A change that moves one must fail here."""

import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from conftest import DATA_DIR, LAB_ROOT

from reqcheck import prd as prdmod
from reqcheck import report, trace
from reqcheck.checks import run_checks
from reqcheck.core import load_lexicon
from reqcheck.sources import load_sources

SOURCES = load_sources(DATA_DIR / "sources")
LEXICON = load_lexicon(DATA_DIR / "lexicon.json")
DRAFT = DATA_DIR / "prd-draft.md"
V1 = DATA_DIR / "prd-v1.md"


@pytest.fixture(scope="module")
def draft():
    return run_checks(prdmod.load(DRAFT), SOURCES, LEXICON)


def test_draft_findings_by_severity(draft):
    assert len(draft.findings) == 50
    assert Counter(f.severity for f in draft.findings) == {"critical": 1, "high": 17, "medium": 32}


def test_draft_findings_by_check(draft):
    assert Counter(f.code for f in draft.findings) == {
        "RQ001": 1, "RQ003": 1, "RQ004": 2, "RQ010": 9, "RQ011": 3, "RQ012": 3, "RQ020": 2, "RQ021": 3,
        "RQ030": 3, "RQ040": 14, "RQ050": 5, "RQ061": 1, "RQ062": 1, "RQ071": 1, "RQ080": 1}


def test_draft_named_findings(draft):
    by = {(f.code, f.item) for f in draft.findings}
    assert ("RQ003", "ESC-R03") in by          # "the workspace Owner": never said
    assert ("RQ001", "ESC-R10") in by          # retries: invented, no source
    assert ("RQ071", "ESC-R06") in by          # SMS: verbatim, from text addressed to AI assistants
    contradictions = sorted(f.message.split(":")[0] for f in draft.findings if f.code == "RQ030")
    assert contradictions == ["ai_p1_starts_escalation", "p1_first_step_minutes", "rule_editors"]
    concepts = Counter(f.message.split()[1].rstrip(",") for f in draft.findings if f.code == "RQ040")
    assert concepts == {"task_priority": 5, "acknowledgement": 4, "on_call_rota": 3, "sms": 1, "business_hours": 1}


def test_one_flagged_block_in_the_sources(draft):
    assert [(f.doc, f.first_line, f.last_line) for f in draft.flags] == [("INT-1", 45, 46)]


def test_v1_has_no_open_findings():
    result = run_checks(prdmod.load(V1), SOURCES, LEXICON)
    assert result.findings == ()


def test_report_prints_the_chapter_tables():
    text, _ = report.render([DRAFT, V1], SOURCES, LEXICON)
    for row in ("| Requirements (functional + NFR) | 14 (11 + 3) | 21 (11 + 10) |",
                "| Acceptance criteria | 12 | 31 |",
                "| Criteria in Given/When/Then form | 9 of 12 | 31 of 31 |",
                "| Source quotes found verbatim | 14 of 15 | 37 of 37 |",
                "| Required NFR categories covered (of 7) | 2 | 7 |",
                "| Requirements with goal, source and test | 11 of 14 (78.6%) | 21 of 21 (100.0%) |",
                "| Decisions recorded | 0 | 8 |",
                "| critical | 1 | 0 |", "| high | 17 | 0 |", "| medium | 32 | 0 |", "| low | 0 | 0 |",
                "| **Total open** | **50** | **0** |",
                "| dependencies | 14 | 0 |", "| clarity | 9 | 0 |"):
        assert row in text, row


def test_impact_of_changing_acknowledgement_and_d1():
    v1 = prdmod.load(V1)
    ack = trace.impact(v1, "ESC-R02")
    assert ack.direct == ("ESC-R02",) and ack.indirect == ("ESC-R04", "ESC-R06", "ESC-R07")
    assert len(ack.tests) == 6
    d1 = trace.impact(v1, "D1")
    assert d1.direct == ("ESC-R04", "ESC-R05") and d1.indirect == () and len(d1.tests) == 4
    int3 = trace.impact(v1, "INT-3")
    assert (len(int3.direct), len(int3.indirect), len(int3.tests)) == (10, 8, 25)


def test_cli_gate_fails_the_draft_and_passes_v1():
    args = ["--sources", str(DATA_DIR / "sources"), "--lexicon", str(DATA_DIR / "lexicon.json")]
    assert report.main(args + [str(DRAFT), "--fail-on", "high"]) == 1
    assert report.main(args + [str(V1), "--fail-on", "low"]) == 0


def test_generator_reproduces_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    committed = sorted(p.relative_to(DATA_DIR).as_posix() for p in DATA_DIR.rglob("*") if p.is_file())
    assert written == committed
    for name in written:
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name
