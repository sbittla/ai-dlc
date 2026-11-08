"""Check an EDL evidence record for completeness (provided).

    python -m audit.evidence ../evidence/evidence-record.yaml

The record is the YAML shape of Chapter 1's Listing 1.1. This checker reads a
small subset of YAML line by line (standard library only): top-level
"key: value" lines and "- name: ..." check entries. It does not judge whether
the evidence is true; it checks that nothing a skeptical colleague would ask
for is blank, and that nobody approved their own change.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ("change", "claim", "spec", "autonomy_tier", "author_of_record", "accepted_by")
REQUIRED_CHECKS = ("failing test", "full suite", "workspace audit", "code review")
TIERS = ("T0", "T1", "T2", "T3", "T4")


def parse(text: str) -> tuple[dict[str, str], list[str]]:
    fields, checks = {}, []
    for line in text.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            value = re.sub(r"(^|\s+)#.*$", "", m.group(2)).strip().strip('"')
            fields[m.group(1)] = value
            continue
        m = re.match(r"^\s*-\s*name:\s*(.+?)\s*$", line)
        if m:
            checks.append(m.group(1).strip('"'))
    return fields, checks


def problems(text: str) -> list[str]:
    fields, checks = parse(text)
    out = [f"field '{k}' is missing or blank" for k in REQUIRED_FIELDS if not fields.get(k)]
    if fields.get("autonomy_tier") and fields["autonomy_tier"] not in TIERS:
        out.append(f"autonomy_tier must be one of {', '.join(TIERS)}")
    names = [c.lower() for c in checks]
    out += [f"no check named like '{c}'" for c in REQUIRED_CHECKS if not any(c in n for n in names)]
    author, acceptor = fields.get("author_of_record"), fields.get("accepted_by")
    if author and acceptor and author == acceptor:
        out.append("accepted_by is the author of record: nobody approves their own change")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Check an evidence record for completeness")
    ap.add_argument("record", type=Path)
    args = ap.parse_args()
    found = problems(args.record.read_text(encoding="utf-8"))
    for p in found:
        print(f"- {p}")
    print(f"evidence record: {len(found)} problem(s)")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
