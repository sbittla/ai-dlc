"""Every number Chapter 9 quotes from Lab 9.1, locked to the reference output.

The reports run <target>/prkit's checks on data/ and the reference repository,
so they also grade your check_pr and verify_claim. To regenerate after a
deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import pytest
from conftest import DATA_DIR, LAB_ROOT, REFERENCE_REPO

from prkit import report

GOLDEN = LAB_ROOT / "tests" / "golden"


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def outputs() -> dict:
    return {
        "incident": lambda: report.report_incident(DATA_DIR),
        "claims": lambda: report.report_claims(DATA_DIR),
        "series": lambda: report.report_series(DATA_DIR, REFERENCE_REPO),
        "release": lambda: report.report_release(REFERENCE_REPO),
    }


@pytest.mark.parametrize("name", ["incident", "claims", "series", "release"])
def test_report_matches_golden(name):
    assert outputs()[name]() == golden(name)
