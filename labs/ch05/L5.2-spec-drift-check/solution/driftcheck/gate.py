"""The CI gate: check one repository for drift and exit with a status CI can act on.

    python -m driftcheck.gate <repo>           # exit 0: no blocking drift; 1: blocking drift; 2: cannot check

Warnings (a test named after a criterion the spec lacks) are printed and do not
fail the gate. Status 2 means a required artifact is missing, so the gate fails
closed instead of passing a repository it could not read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compare import CHECKS, Drift, detect
from .extract import Facts, extract


def missing(facts: Facts) -> list[str]:
    out = []
    if not facts.spec_version:
        out.append("spec (specs/*/spec.md with a Version: line)")
    if not facts.contract_fields:
        out.append("contract (the Contract: file the spec names)")
    if not facts.code_fields:
        out.append("code (dataclasses in src/relay/escalation/)")
    if not facts.test_versions:
        out.append("tests (tests/escalation/test_*.py)")
    return out


def check(repo: Path) -> tuple[int, list[Drift], list[str]]:
    facts = extract(repo)
    gaps = missing(facts)
    if gaps:
        return 2, [], gaps
    found = detect(facts)
    return (1 if any(d.blocking for d in found) else 0), found, []


def render(found: list[Drift], gaps: list[str], status: int) -> str:
    lines = [f"- cannot read {g}" for g in gaps]
    for d in found:
        lines.append(f"- **{d.code}** ({'blocks' if d.blocking else 'warns'}) {d.item}: {d.message}"
                     f" — {CHECKS[d.code][1]}")
    verdict = {0: "PASS", 1: "FAIL", 2: "ERROR"}[status]
    blocking = sum(d.blocking for d in found)
    lines.append(f"Drift gate: {verdict} ({blocking} blocking, {len(found) - blocking} warning(s))")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="driftcheck.gate")
    ap.add_argument("repo", type=Path)
    status, found, gaps = check(ap.parse_args(argv).repo)
    sys.stdout.write(render(found, gaps, status))
    return status


if __name__ == "__main__":
    sys.exit(main())
