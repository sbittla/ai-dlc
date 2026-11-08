"""Show the due date every supported time zone would display for one stored date.

    python tools/due_date_table.py --date 2026-11-20

Run it before and after a change to display_due_date. Rows marked "<-- differs"
are viewers who see a different date from the one stored.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from relay.duedates import display_due_date  # noqa: E402
from relay.timezones import OFFSETS  # noqa: E402


def table(stored: date) -> tuple[list[str], int]:
    lines = ["| Viewer time zone | UTC offset | Shown |", "| --- | ---: | --- |"]
    differs = 0
    for zone, minutes in sorted(OFFSETS.items(), key=lambda kv: (kv[1], kv[0])):
        shown = display_due_date(stored, zone)
        sign = "+" if minutes >= 0 else "-"
        offset = f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
        mark = "  <-- differs" if shown != stored else ""
        differs += shown != stored
        lines.append(f"| {zone} | {offset} | {shown.isoformat()}{mark} |")
    return lines, differs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default="2026-11-20", help="stored due date, YYYY-MM-DD")
    args = ap.parse_args()
    stored = date.fromisoformat(args.date)
    lines, differs = table(stored)
    print(f"Stored due date: {stored.isoformat()}")
    print("\n".join(lines))
    print(f"Zones showing a different date: {differs} of {len(OFFSETS)}")


if __name__ == "__main__":
    main()
