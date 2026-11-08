"""Every number Chapter 7 quotes from Lab 7.1, locked to the reference output.

The reports in tests/golden/ were printed by the reference solution. Any change to
the data, the simulator, the policy or the statistics that moves a quoted number
fails here. To regenerate after a deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import pytest
from conftest import DATA_DIR, LAB_ROOT

from evalsuite import report

GOLDEN = LAB_ROOT / "tests" / "golden"
REPORTS = ["dataset", "incident", "candidates", "leakage", "router", "stats", "agents"]
GATES = {"sim-large:triage-v2": 1, "sim-large:triage-v3.1": 0, "sim-large-2:triage-v1": 1}


@pytest.fixture(scope="module")
def suite():
    return report.Suite(DATA_DIR)


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


@pytest.mark.parametrize("name", REPORTS)
def test_report_matches_golden(suite, name):
    fn = getattr(report, f"report_{name}")
    assert fn(suite) == golden(name)


@pytest.mark.parametrize("candidate", sorted(GATES))
def test_gate_matches_golden_and_exit_code(suite, candidate):
    text, code = report.report_gate(suite, report.BASELINE, candidate)
    assert text == golden("gate_" + candidate.replace(":", "_"))
    assert code == GATES[candidate]


def test_headline_numbers(suite):
    """The handful of numbers the chapter's narrative leans on, checked directly."""
    from evalsuite import runner
    prod = {t["id"] for t in suite.held if t["source"] == "production"}
    v1, v2 = suite.records("sim-large:triage-v1"), suite.records("sim-large:triage-v2")
    assert round(runner.accuracy_on(v1, prod) * 100, 1) == 85.1
    assert round(runner.accuracy_on(v2, prod) * 100, 1) == 70.5
    g = suite.gate(report.BASELINE, "sim-large:triage-v2")
    assert (round(g.overall.diff * 100, 1), round(g.overall.low * 100, 1), round(g.overall.high * 100, 1)) == (-9.5, -14.0, -4.8)
    assert (g.overall.worse, g.overall.better) == (26, 6)


def test_gate_cli_exit_code():
    import os
    import subprocess
    import sys
    target = os.environ.get("LAB_TARGET", "starter")
    run = subprocess.run([sys.executable, "-m", "evalsuite.report", "--data", str(DATA_DIR), "gate",
                          "--candidate", "sim-large:triage-v2"], cwd=LAB_ROOT / target, capture_output=True, text=True)
    if "NotImplementedError" in run.stderr:
        raise NotImplementedError("the gate CLI needs the TODO functions")
    assert run.returncode == 1 and "Decision: **FAIL**" in run.stdout
