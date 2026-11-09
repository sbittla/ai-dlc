"""Every number Chapter 10 quotes from Lab 10.1, locked to the reference output.

The reports run <target>'s designs and comparison on data/, so they also grade your run_workflow and compare.
To regenerate after a deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

from types import SimpleNamespace

import pytest
from conftest import LAB_ROOT

from agentlab import report

GOLDEN = LAB_ROOT / "tests" / "golden"
NAMES = ["incident", "budgets", "compare-heldout", "compare-dev", "paired-heldout", "paired-dev", "slices-heldout",
         "trajectory-heldout"]


def outputs() -> dict:
    out = {}
    for name in NAMES:
        kind, _, split = name.partition("-")
        out[name] = (lambda k=kind, s=split: report.REPORTS[k](SimpleNamespace(split=s or "heldout")))
    return out


@pytest.mark.parametrize("name", NAMES)
def test_report_matches_golden(name):
    assert outputs()[name]() == (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")
