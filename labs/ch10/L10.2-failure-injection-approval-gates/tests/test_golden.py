"""Every number Chapter 10 quotes from Lab 10.2, locked to the reference output.

    cd solution
    python ../scripts/update_golden.py
"""

from conftest import LAB_ROOT

from faultlab import report


def outputs() -> dict:
    return {"drills": report.report}


def test_report_matches_golden():
    assert report.report() == (LAB_ROOT / "tests" / "golden" / "drills.md").read_text(encoding="utf-8").rstrip("\n")
