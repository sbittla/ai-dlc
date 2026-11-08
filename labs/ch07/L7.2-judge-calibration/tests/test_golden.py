"""Every number Chapter 7 quotes from Lab 7.2, locked to the reference output.

To regenerate after a deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import pytest
from conftest import DATA_DIR, LAB_ROOT

from judgecal import policy, report

GOLDEN = LAB_ROOT / "tests" / "golden"


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def outputs() -> dict[str, callable]:
    a, p = report.load(DATA_DIR)
    pol = policy.load_policy(DATA_DIR / "judge-policy.json")
    return {
        "agreement": lambda: report.report_agreement(a, p),
        "probes": lambda: report.report_probes(a, p, "heldout"),
        "probes_calibration": lambda: report.report_probes(a, p, "calibration"),
        "decide": lambda: report.report_decide(a, p, pol),
    }


@pytest.mark.parametrize("name", ["agreement", "probes", "probes_calibration", "decide"])
def test_report_matches_golden(name):
    assert outputs()[name]() == golden(name)


def test_pin_is_checked():
    pol = policy.load_policy(DATA_DIR / "judge-policy.json")
    assert report.verify_pin(DATA_DIR, pol) == "relay-assistant-judge-calibration 2026.11.1"
