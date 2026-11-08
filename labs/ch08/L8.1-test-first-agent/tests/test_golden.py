"""Every number Chapter 8 quotes from Lab 8.1, locked to the reference output.

The incident and grade reports run the reference repository's tests through
<target>/testfirst, so they also check your oracle check. To regenerate after a
deliberate change (and then update the chapter):

    cd solution
    python ../scripts/update_golden.py
"""

import pytest
from conftest import LAB_ROOT, REFERENCE_REPO

from testfirst import report

GOLDEN = LAB_ROOT / "tests" / "golden"


def golden(name: str) -> str:
    return (GOLDEN / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")


def outputs() -> dict:
    return {
        "incident": lambda: report.report_incident(REFERENCE_REPO),
        "grade": lambda: report.report_grade(REFERENCE_REPO, ("hours", "delivery"))[0],
        "release": lambda: report.report_release(REFERENCE_REPO),
    }


@pytest.mark.parametrize("name", ["incident", "grade", "release"])
def test_report_matches_golden(name):
    assert outputs()[name]() == golden(name)
