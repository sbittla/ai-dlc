"""Golden tests: every number Chapter 11 quotes from Lab 11.1. A change that moves one must fail here."""

import os
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from conftest import DATA_DIR, LAB_ROOT, POLICY, PRICES, TARGET

from cloudcheck.cost import estimate
from cloudcheck.plan import load_json, load_plan, resources
from cloudcheck.policy import gate_status, run_policy
from cloudcheck.report import evaluate_seeded, render_cost, render_incident, render_seeded
from cloudcheck.teardown import check_teardown, ready

AS_OF = date(2026, 11, 30)
NONPROD = load_plan(DATA_DIR / "plans" / "relay-nonprod.plan.json")
INCIDENT = load_plan(DATA_DIR / "plans" / "incident-lab.plan.json")
TEARDOWN = DATA_DIR / "teardown"


def test_relay_nonprod_passes_with_one_waiver():
    findings = run_policy(NONPROD, POLICY, AS_OF)
    assert len(resources(NONPROD)) == 95
    assert [(f.rule, f.address, f.status) for f in findings] == [
        ("POL007", "aws_iam_role_policy.ci_apply", "waived"), ("POL007", "aws_iam_role_policy.ci_apply", "waived")]
    assert gate_status(findings) == 0


def test_the_waiver_expires():
    findings = run_policy(NONPROD, POLICY, date(2027, 3, 1))
    assert (sum(f.status == "fail" for f in findings), gate_status(findings)) == (2, 1)


def test_relay_nonprod_fixed_cost():
    est = estimate(NONPROD, PRICES)
    cats = {k: round(v * 730, 2) for k, v in est.by_category().items() if v}
    assert (round(est.hourly, 4), round(est.monthly, 2)) == (0.304, 221.9)
    assert cats == {"compute": 43.25, "database": 51.32, "network": 125.92, "security": 1.4}
    shares = {k: round(100 * v / est.hourly, 1) for k, v in est.by_category().items() if v}
    assert shares == {"compute": 19.5, "database": 23.1, "network": 56.7, "security": 0.6}
    text = render_cost(NONPROD, PRICES, "nonprod", None, 300, False)
    assert "Interface endpoints: $0.10 per hour, 32.9% of the fixed cost." in text
    assert len(est.usage) == 11 and est.unpriced == []


def test_incident_environment():
    findings = run_policy(INCIDENT, POLICY, AS_OF)
    failing = [f for f in findings if f.status == "fail"]
    assert len(resources(INCIDENT)) == 9
    assert Counter(f.rule for f in failing) == {"POL001": 2, "POL002": 3, "POL003": 2, "POL005": 4, "POL006": 6,
                                                "POL007": 1, "POL008": 2, "POL009": 1, "POL010": 1, "POL011": 3,
                                                "POL012": 3}
    est = estimate(INCIDENT, PRICES)
    assert (round(est.hourly, 2), round(est.hourly * 66, 2)) == (34.68, 2289.01)
    assert round(100 * est.by_category()["compute"] / est.hourly, 1) == 93.9
    text = render_incident(load_json(DATA_DIR / "incident.json"), DATA_DIR / "incident.json", POLICY, PRICES, AS_OF)
    assert "to Mon 09 Nov 2026 10:15 UTC: 66 hours." in text
    assert "$34.68 per hour; $2,289.01 for the weekend" in text
    assert "28 failing across 11 of 12 rules" in text
    assert "crossed 50% after 4.3 h, 80% after 6.9 h, 100% after 8.7 h" in text


def test_seeded_results():
    rows, summary = evaluate_seeded(NONPROD, DATA_DIR / "seeded", POLICY, AS_OF)
    assert {r["id"]: r["outcome"] for r in rows} == {
        **{f"S{n:02d}": "detected" for n in range(1, 13)}, "S13": "cannot check (fails closed)",
        "S14": "missed", "S15": "missed", "C01": "clean (control)"}
    assert summary == {"cases": 16, "violations": 14, "unknown": 1, "controls": 1, "detected": 12, "missed": 2,
                       "cannot check": 1, "controls clean": 1, "false alarms": 0}
    assert {r["id"]: r["gate"] for r in rows if r["id"] in ("S02", "S13", "S14")} == {"S02": 1, "S13": 2, "S14": 0}
    assert [r["new_findings"] for r in rows if r["id"] in ("S04", "S08")] == [75, 2]
    assert ("Seeded violations: 14; detected 12, missed 2. Unknown until apply: 1, failed closed 1. "
            "Controls clean: 1 of 1. False alarms: 0.") in render_seeded(rows, summary)


@pytest.mark.parametrize("stem, expected", [
    ("relay-nonprod", []),
    ("T1-protection-still-on", [("TD003", "destroy will fail: deletion protection is on")]),
    ("T2-deletes-a-shared-database", [("TD002", "would delete a resource tagged env=shared, app=test-data"),
                                      ("TD003", "no final snapshot: the data is deleted with the database")]),
    ("T3-no-final-snapshot", [("TD003", "no final snapshot: the data is deleted with the database")]),
    ("T4-targeted-destroy-leaves-nat", [("TD001", "not deleted"), ("TD001", "not deleted")]),
])
def test_teardown_plans(stem, expected):
    found = check_teardown(NONPROD, load_plan(TEARDOWN / f"{stem}.destroy.plan.json"), "nonprod")
    assert [(f.rule, f.message) for f in found] == expected
    assert ready(found) is (expected == [])


def test_teardown_inventories():
    destroy = load_plan(TEARDOWN / "relay-nonprod.destroy.plan.json")
    clean = check_teardown(NONPROD, destroy, "nonprod", inventory=load_json(TEARDOWN / "inventory-after-teardown.json"),
                           as_of=date(2026, 12, 1))
    left = check_teardown(NONPROD, destroy, "nonprod",
                          inventory=load_json(TEARDOWN / "inventory-after-teardown-leftovers.json"),
                          as_of=date(2026, 12, 1))
    assert clean == []
    assert [f.message for f in left] == ["left behind", "left behind", "retained with no expires tag"]


def test_gate_exit_codes_from_the_command_line():
    run_policy(NONPROD, POLICY, AS_OF)  # needs TODO 1-5

    def gate(*args):
        env = dict(os.environ, PYTHONPATH=str(LAB_ROOT / TARGET))
        return subprocess.run([sys.executable, "-m", "cloudcheck.report", "check", *args, "--gate"],
                              capture_output=True, text=True, env=env, cwd=LAB_ROOT / TARGET).returncode
    plan = str(Path("..") / "data" / "plans" / "relay-nonprod.plan.json")
    assert gate(plan) == 0
    assert gate(plan, "--overlay", str(Path("..") / "data" / "seeded" / "S02.overlay.json")) == 1
    assert gate(plan, "--overlay", str(Path("..") / "data" / "seeded" / "S13.overlay.json")) == 2
    assert gate(plan, "--overlay", str(Path("..") / "data" / "seeded" / "S15.overlay.json")) == 0  # drift: invisible
    assert gate(str(Path("..") / "data" / "plans" / "incident-lab.plan.json")) == 1
