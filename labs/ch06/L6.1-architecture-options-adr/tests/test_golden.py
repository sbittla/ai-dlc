"""Golden tests: every number Chapter 6 quotes from Lab 6.1. A change that moves one must fail here."""

import subprocess
import sys
from collections import Counter

import pytest
from conftest import DATA_DIR, LAB_ROOT, RELAY

from archscore import report, structure
from archscore.checks import check_adr, check_threat_model
from archscore.docs import load_adr, load_threat_model
from archscore.model import apply_scenario, load_catalogue, load_options
from archscore.scoring import head_to_head, rank, weight_to_flip, weighted_score

CAT = load_catalogue(DATA_DIR / "drivers.json")
OPTION_FILES = [DATA_DIR / "options" / "A-modular-monolith.json", DATA_DIR / "options" / "B-microservices.json"]
OPTIONS = load_options(OPTION_FILES)
A, B = OPTIONS
ADR_DIR = RELAY / "docs" / "adr"
ADR_007 = ADR_DIR / "ADR-007-modular-monolith-async-triage.md"


def test_catalogue_has_the_prd_nfrs_and_six_constraints():
    ids = [d.id for d in CAT.drivers]
    assert ids[:10] == [f"ESC-N{n:02d}" for n in range(1, 11)]
    assert ids[10:] == [f"CON-{n}" for n in range(1, 7)]
    assert sorted(CAT.decisions) == [f"D{n}" for n in range(1, 10)]
    assert [d.id for d in CAT.drivers if d.weight == 0] == ["ESC-N02", "ESC-N08"]
    assert [d.id for d in CAT.drivers if d.must] == ["ESC-N01", "ESC-N03", "ESC-N07", "CON-4"]


def test_weighted_totals():
    assert (weighted_score(A, CAT.drivers).total, weighted_score(A, CAT.drivers).maximum) == (75, 93)
    assert weighted_score(B, CAT.drivers).total == 52
    assert (weighted_score(A, CAT.drivers).percent, weighted_score(B, CAT.drivers).percent) == (80.6, 55.9)


def test_ranking_and_head_to_head():
    assert [r.option_id for r in rank(OPTIONS, CAT.drivers)] == ["A", "B"]
    h = head_to_head(A, B, CAT.drivers)
    assert (len(h["A"]), h["B"], len(h["equal"])) == (7, ["CON-3", "CON-6"], 5)


def test_no_single_weight_flips_the_ranking():
    assert set(weight_to_flip(A, B, CAT.drivers).values()) == {None}


def test_structure():
    ma, mb = structure.metrics(A), structure.metrics(B)
    assert (ma["deployable units"], mb["deployable units"]) == (1, 5)
    assert (ma["process types"], mb["process types"]) == (2, 5)
    assert (ma["databases"], mb["databases"], mb["message brokers"]) == (1, 4, 1)
    assert (ma["trust boundaries"], mb["trust boundaries"]) == (4, 6)
    assert (ma["flows crossing a boundary"], mb["flows crossing a boundary"]) == (4, 12)
    assert (ma["components a step needs"], mb["components a step needs"]) == (2, 7)
    assert round(ma["step path down, minutes per 30 days"], 1) == 86.4
    assert round(mb["step path down, minutes per 30 days"], 1) == 301.5


def test_scenario_five_teams_reverses_the_ranking():
    cat, opts, _ = apply_scenario(CAT, OPTIONS, DATA_DIR / "scenarios" / "five-teams.json")
    a, b = opts
    assert (weighted_score(a, cat.drivers).total, weighted_score(b, cat.drivers).total) == (70, 78)
    assert weighted_score(a, cat.drivers).maximum == 102
    assert [r.option_id for r in rank(opts, cat.drivers)] == ["B", "A"]


def test_score_report_prints_the_chapter_numbers():
    text = report.render_scores(CAT, OPTIONS)
    for line in ("| **Weighted total** | | | | **75 of 93 (80.6%)** | **52 of 93 (55.9%)** |",
                 "Gap: 23 points. Option A scores higher on 7 drivers, Option B on 2 (CON-3, CON-6), equal on 5",
                 "- No single weight from 0 to 5 makes Option B win.",
                 "- Nearest: CON-3, where Option B leads by 1; its weight would have to rise by 24, from 1 to 25.",
                 "| deployable units | 1 | 5 |", "| process types | 2 | 5 |", "| databases | 1 | 4 |", "| trust boundaries | 4 | 6 |",
                 "| flows crossing a boundary | 4 | 12 |", "| components a step needs | 2 | 7 |",
                 "| step-path availability | 99.80% | 99.30% |",
                 "| step path down, minutes per 30 days | 86.4 | 301.5 |"):
        assert line in text, line


def test_availability_explain_prints_equation_6_1():
    text = report.render_availability(OPTIONS)
    assert "- Option A: 2 components at 99.9% -> 99.80% (0.998001); down 86.4 minutes per 30 days" in text
    assert "- Option B: 7 components at 99.9% -> 99.30% (0.993021); down 301.5 minutes per 30 days" in text
    assert "- One component at 99.9%: down 43.2 minutes per 30 days" in text


def test_the_agent_draft_adr_has_six_findings():
    found = check_adr(load_adr(DATA_DIR / "adr" / "ADR-007-draft.md"), CAT)
    assert Counter(f.code for f in found) == {"ADR001": 1, "ADR003": 1, "ADR006": 1, "ADR007": 2, "ADR009": 1}


def test_relay_adrs_pass_the_checker():
    for path in sorted(ADR_DIR.glob("ADR-*.md")):
        assert check_adr(load_adr(path), CAT) == [], path.name


def test_adr_007_quotes_the_tool_and_lists_three_rejected_alternatives():
    adr = load_adr(ADR_007)
    assert adr.options == ["A", "B", "C", "D"] and sorted(adr.rejected) == ["B", "C", "D"]
    assert {"D3", "D5", "D7", "D8", "D9"} <= set(adr.links)
    text = ADR_007.read_text(encoding="utf-8")
    for quoted in ("75 of 93", "52 of 93", "No single weight from 0 to 5", "2\ninternal components",
                   "7 in Option B", "86.4 against 301.5", "4.12 s"):
        assert quoted in text, quoted


def test_threat_models():
    opts = {o.id: o for o in OPTIONS}
    tms = {p.stem: load_threat_model(p) for p in sorted((DATA_DIR / "threat-models").glob("*.md"))}
    assert {k: len(v.threats) for k, v in tms.items()} == {
        "A-draft": 4, "A-modular-monolith": 13, "B-microservices": 14}
    assert check_threat_model(tms["A-modular-monolith"], opts["A"]) == []
    assert check_threat_model(tms["B-microservices"], opts["B"]) == []
    draft = check_threat_model(tms["A-draft"], opts["A"])
    assert [f.code for f in draft] == ["TM001", "TM005", "TM006", "TM007"]
    no_evidence_yet = sum(t.evidence.startswith("None yet") for t in tms["B-microservices"].threats)
    assert no_evidence_yet == 13


def test_gate_exit_codes():
    check_adr(load_adr(ADR_007), CAT)  # the gate runs the checker; finish TODO 4 and 5 first
    check_threat_model(load_threat_model(DATA_DIR / "threat-models" / "A-draft.md"), A)

    def run(*args):
        return subprocess.run([sys.executable, "-m", "archscore.report", *args],
                              capture_output=True, text=True, env=_env()).returncode
    drivers = str(DATA_DIR / "drivers.json")
    assert run("adr", "--drivers", drivers, str(ADR_007), "--gate") == 0
    assert run("adr", "--drivers", drivers, str(DATA_DIR / "adr" / "ADR-007-draft.md"), "--gate") == 1
    assert run("threats", "--options", str(DATA_DIR / "options"),
               str(DATA_DIR / "threat-models" / "A-draft.md"), "--gate") == 1


def _env():
    import os
    from conftest import TARGET
    return dict(os.environ, PYTHONPATH=str(LAB_ROOT / TARGET))


@pytest.mark.parametrize("name", ["drivers.json", "options/A-modular-monolith.json", "adr/ADR-007-draft.md",
                                  "threat-models/B-microservices.md"])
def test_data_is_committed(name):
    assert (DATA_DIR / name).is_file()
