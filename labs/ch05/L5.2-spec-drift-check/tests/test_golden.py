"""Golden tests: every number Chapter 5 quotes from Lab 5.2. A change that moves one must fail here."""

import shutil
import subprocess
import sys

import pytest
from conftest import BASELINE, DATA_DIR, LAB_ROOT, SCENARIOS

from driftcheck import gate, report
from driftcheck.compare import CHECKS
from driftcheck.extract import extract

EXPECTED = {
    "00-baseline": ([], 0),
    "01-unit-renamed-in-code": ([("DR010", "Step.delay_minutes"), ("DR011", "Step.delay_seconds")], 1),
    "02-contract-field-added": ([("DR010", "Evaluation.task_title"), ("DR013", "Evaluation.task_title")], 1),
    "03-spec-bumped": ([("DR001", "version"), ("DR030", "ESC-AC12")], 1),
    "04-status-added-in-code": ([("DR020", "STATUSES")], 1),
    "05-type-drift": ([("DR012", "Step.delay_minutes")], 1),
    "06-unspecified-test": ([("DR031", "ESC-AC15")], 0),
    "07-boundary-moved": ([], 0),
    "08-criterion-weakened": ([], 0),
}
SUITES = {"00-baseline": "64 passed", "01-unit-renamed-in-code": "12 failed, 52 passed",
          "02-contract-field-added": "3 failed, 61 passed", "03-spec-bumped": "1 failed, 63 passed",
          "04-status-added-in-code": "1 failed, 63 passed", "05-type-drift": "64 passed",
          "06-unspecified-test": "65 passed", "07-boundary-moved": "3 failed, 61 passed",
          "08-criterion-weakened": "64 passed"}


@pytest.fixture(scope="module")
def rows():
    return report.evaluate(BASELINE, SCENARIOS, with_tests=True)


def test_baseline_facts():
    facts = extract(BASELINE)
    assert (facts.spec_version, facts.contract_version, facts.code_version) == ("1.0.0", "1.0.0", "1.0.0")
    assert len(facts.contract_fields) == len(facts.code_fields) == 20 and len(facts.criteria) == 12
    assert sorted(facts.contract_enums) == ["ERROR_CODES", "RULE_PRIORITIES", "STATUSES"]
    assert len(CHECKS) == 9 and [c for c, (blocks, _) in CHECKS.items() if not blocks] == ["DR031"]


def test_every_scenario(rows):
    got = {r["id"]: ([(d.code, d.item) for d in r["drift"]], r["status"]) for r in rows}
    assert got == EXPECTED


def test_test_suites_per_scenario(rows):
    assert {r["id"]: r["tests"] for r in rows} == SUITES


def test_summary(rows):
    assert report.summary(rows) == {"scenarios": 9, "structural": 6, "behavioural": 2, "structural_found": 6,
                                    "behavioural_found": 0, "gate_failed": 5, "behavioural_caught_by_tests": 1}
    text = report.render(rows)
    assert "Structural drifts seeded: 6; found by the gate: 6" in text
    assert "Behavioural drifts caught by the test suite: 1 of 2" in text


def test_gate_exit_codes(tmp_path):
    assert gate.main([str(BASELINE)]) == 0
    repo = report.materialize(BASELINE, SCENARIOS / "03-spec-bumped", tmp_path)
    assert gate.main([str(repo)]) == 1
    shutil.rmtree(repo / "tests" / "escalation")
    assert gate.main([str(repo)]) == 2  # fails closed when an artifact is missing


def test_generator_reproduces_data_byte_for_byte(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    committed = sorted(p.relative_to(DATA_DIR).as_posix() for p in SCENARIOS.rglob("*") if p.is_file())
    assert written == committed and len(written) == 20
    for name in written:
        assert (tmp_path / name).read_bytes() == (DATA_DIR / name).read_bytes(), name
