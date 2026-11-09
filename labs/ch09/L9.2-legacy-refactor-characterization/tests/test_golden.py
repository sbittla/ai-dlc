"""Every number Chapter 9 quotes from Lab 9.2, locked to the reference output.

The reports run <target>/modernize's functions on data/, so they also grade
your work. The parallel report integrates five worktrees and runs the
characterization and the notify tests after each step (about ten seconds).
To regenerate after a deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import pytest
from conftest import DATA_DIR, LAB_ROOT

from modernize import report

GOLDEN = LAB_ROOT / "tests" / "golden"


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def outputs() -> dict:
    return {
        "incident": lambda: report.report_incident(DATA_DIR),
        "characterize": lambda: report.report_characterize(DATA_DIR),
        "parallel": lambda: report.report_parallel(DATA_DIR),
    }


@pytest.mark.parametrize("name", ["incident", "characterize", "parallel"])
def test_report_matches_golden(name):
    assert outputs()[name]() == golden(name)
