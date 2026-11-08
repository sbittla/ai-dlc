"""Every number Chapter 8 quotes from Lab 8.2, locked to the reference output, and your repair graded.

The reports run through <target>/mutate, so they also check your operators and
score. They are slow (about a minute each): the mutation runs are real. To
regenerate after a deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import functools
import json

import pytest
from conftest import CORE, DATA_DIR, LAB_ROOT, TARGET_DIR

from mutate import report

GOLDEN = LAB_ROOT / "tests" / "golden"
REFERENCE_SUITE = LAB_ROOT / "solution" / "suite" / "test_repaired.py"


def policy(modules: str | None = None) -> dict:
    p = json.loads((DATA_DIR / "mutation-policy.json").read_text(encoding="utf-8"))
    if modules:
        p["targets"] = [f"relay.escalation.{m}" for m in modules.split(",")]
    return p


@functools.lru_cache(maxsize=None)
def run(name: str) -> tuple[str, bool]:
    if name == "agent":
        return report.report(DATA_DIR, [DATA_DIR / "weak-suite" / "test_agent_suite.py"], policy(CORE), "agent")
    if name == "repaired":
        return report.report(DATA_DIR, [REFERENCE_SUITE], policy(CORE), "repaired")
    if name == "relay":
        return report.report(DATA_DIR, report.suite_files(DATA_DIR, "relay", LAB_ROOT), policy(), "relay")
    raise KeyError(name)


def outputs() -> dict:
    return {name: (lambda n=name: run(n)[0]) for name in ("agent", "repaired", "relay")}


@pytest.mark.parametrize("name", ["agent", "repaired", "relay"])
def test_report_matches_golden(name):
    assert run(name)[0] == (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def test_the_agent_suite_fails_the_gate_and_the_reference_repair_passes():
    assert run("agent")[1] is False and run("repaired")[1] is True and run("relay")[1] is True


def test_your_repaired_suite_passes_the_gate():
    mine = TARGET_DIR / "suite" / "test_repaired.py"
    text = mine.read_text(encoding="utf-8")
    if "def test_repairs_written" in text:
        raise NotImplementedError("Lab 8.2 steps 4 to 6: repair suite/test_repaired.py, then delete "
                                  "test_repairs_written")
    if mine.resolve() == REFERENCE_SUITE.resolve():
        passed = run("repaired")[1]
    else:
        passed = report.report(DATA_DIR, [mine], policy(CORE), "yours")[1]
    assert passed, "run: python -m mutate.report --data ../data --suite repaired --modules rules,evaluate,hours"


def test_your_repaired_suite_has_properties():
    text = (TARGET_DIR / "suite" / "test_repaired.py").read_text(encoding="utf-8")
    if "def test_repairs_written" in text:
        raise NotImplementedError("Lab 8.2 step 5: add at least two properties with props.for_all")
    assert text.count("@for_all(") >= 2
