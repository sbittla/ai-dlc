"""Golden tests: every number Chapter 6 quotes from Lab 6.2. A change that moves one must fail here."""

import json
import os
import subprocess
import sys

import pytest
from conftest import DATA_DIR, LAB_ROOT, TARGET

from fitcheck.graph import build_graph, load_tree
from fitcheck.report import check, evaluate_seeded, render_seeded
from fitcheck.rules import run_rules

REPO = DATA_DIR / "relay-repo"
RULES = json.loads((DATA_DIR / "rules.json").read_text(encoding="utf-8"))
SEEDED = DATA_DIR / "seeded"


def test_relay_copy_is_4_19_0():
    assert 'version = "4.19.0"' in (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_clean_relay_passes_every_rule():
    graph, findings = check(REPO, RULES)
    assert findings == []
    assert (len(graph), sum(len(v) for v in graph.values())) == (17, 81)


def test_six_rules_each_linked_to_an_adr():
    ids = [r["id"] for r in RULES["layers"]] + [RULES[k]["id"] for k in ("network", "dependencies", "cycles")]
    assert ids == ["FF001", "FF002", "FF003", "FF004", "FF005", "FF006"]
    adrs = {r["adr"] for r in RULES["layers"]} | {RULES[k]["adr"] for k in ("network", "dependencies", "cycles")}
    assert adrs == {"ADR-007", "ADR-008"}


def test_seeded_results():
    rows, summary = evaluate_seeded(REPO, RULES, SEEDED)
    assert {r["id"]: r["outcome"] for r in rows} == {
        "V01": "detected", "V02": "detected", "V03": "detected", "V04": "detected", "V05": "detected",
        "V06": "detected", "V07": "clean (control)", "V08": "missed", "V09": "missed", "V10": "flagged by design"}
    assert summary == {"cases": 10, "violations": 9, "caught": 7, "missed": 2, "controls clean": 1,
                       "false alarms": 0}
    text = render_seeded(rows, summary, 0)
    assert "Seeded violations: 9; caught 7, missed 2. Controls clean: 1. False alarms: 0." in text


def test_v03_fires_two_rules_with_the_cycle_named():
    _, findings = check(REPO, RULES, SEEDED / "V03")
    assert [(f.rule, f.message) for f in findings] == [
        ("FF003", "imports relay.service.app"),
        ("FF006", "cycle: relay.service.app -> relay.worker -> relay.worker.runner")]


def test_gate_exit_codes():
    run_rules(build_graph(load_tree(REPO)), load_tree(REPO), RULES)  # needs TODO 1-4

    def gate(*extra):
        env = dict(os.environ, PYTHONPATH=str(LAB_ROOT / TARGET))
        return subprocess.run([sys.executable, "-m", "fitcheck.report", "--repo", str(REPO), "--rules",
                               str(DATA_DIR / "rules.json"), "--gate", *extra],
                              capture_output=True, text=True, env=env).returncode
    assert gate() == 0
    assert gate("--overlay", str(SEEDED / "V02")) == 1
    assert gate("--overlay", str(SEEDED / "V07")) == 0
    assert gate("--overlay", str(SEEDED / "V08")) == 0   # the blind spot passes the gate


@pytest.mark.parametrize("case", ["V01", "V05", "V09"])
def test_overlays_are_committed(case):
    assert (SEEDED / case).is_dir()
