"""A check for blameless postmortems (TODO 4: `check`).

Rules (each finding is (code, detail)):

- PM001 a required section is missing (one finding per section, in REQUIRED order).
- PM002 a timeline line (a "- " bullet under Timeline) has no "[ref: ...]".
- PM003 blame language anywhere: any phrase in BLAME, matched case-insensitively (one finding per phrase found).
- PM004 an action item (a table row under Action items, after the header and separator) has an empty Owner or Due.
- PM005 an action item's Type is not one of TYPES.
- PM006 a person in `people` is named under Contributing factors (people are not causes; systems are).
- PM007 "root cause" appears under Diagnosis on a line that does not say "supported".
"""

from __future__ import annotations

import re

REQUIRED = ("Summary", "Impact", "Timeline", "Detection", "Diagnosis", "Contributing factors", "What went well",
            "Action items")
BLAME = ("human error", "should have known", "careless", "negligent", "fault of", "blame")
TYPES = ("spec", "test", "eval", "adversarial-eval", "detection", "runbook")


def sections(text: str) -> dict[str, list[str]]:
    """Lines under each `## ` heading (provided)."""
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def check(text: str, people: list[str]) -> list[tuple[str, str]]:
    """TODO 4. Every finding of PM001 to PM007, in rule order, then in the order found."""
    raise NotImplementedError("TODO 4: check")
