"""Regenerate tests/golden/ from the reference solution (instructors only).

Run from solution/ after a deliberate change to data, simulator, policy or statistics:

    cd solution
    python ../scripts/update_golden.py

Then re-check every number Chapter 7 quotes against the new files.
"""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "solution"))

from evalsuite import report  # noqa: E402

sys.path.insert(0, str(LAB / "tests"))
from test_golden import GATES, REPORTS  # noqa: E402


def main() -> None:
    suite = report.Suite(LAB / "data")
    out = LAB / "tests" / "golden"
    out.mkdir(exist_ok=True)
    for name in REPORTS:
        (out / f"{name}.md").write_text(getattr(report, f"report_{name}")(suite) + "\n", encoding="utf-8", newline="\n")
    for cand in GATES:
        text, _ = report.report_gate(suite, report.BASELINE, cand)
        (out / f"gate_{cand.replace(':', '_')}.md").write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(REPORTS) + len(GATES)} golden files to {out}")


if __name__ == "__main__":
    main()
