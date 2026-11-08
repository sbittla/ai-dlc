"""Print the workspace audit for one or more repositories (provided).

    python -m audit.report --policy ../data/policy.json --as-of 2026-11-08 \
        ../data/repos/before ../data/repos/after

Columns are repositories, in the order given. With --fail-on high, the exit
status is 1 if any repository has an open finding of that severity or worse,
which is how the audit runs as a CI status check.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .checks import AuditResult, run_audit
from .core import AREAS, CHECKS, SEVERITIES, load_json, load_policy


def summary_table(results: list[AuditResult]) -> list[str]:
    head = "| Open findings | " + " | ".join(r.repo for r in results) + " |"
    lines = [head, "| --- |" + " ---: |" * len(results)]
    for sev in SEVERITIES:
        lines.append(f"| {sev} | " + " | ".join(str(sum(f.severity == sev for f in r.open)) for r in results) + " |")
    lines.append("| **Total open** | " + " | ".join(f"**{len(r.open)}**" for r in results) + " |")
    lines.append("| Waived (with owner and expiry) | " + " | ".join(str(len(r.waived)) for r in results) + " |")
    return lines


def area_table(results: list[AuditResult]) -> list[str]:
    lines = ["| Open findings by area | " + " | ".join(r.repo for r in results) + " |",
             "| --- |" + " ---: |" * len(results)]
    for area in AREAS:
        lines.append(f"| {area} | " + " | ".join(str(sum(f.area == area for f in r.open)) for r in results) + " |")
    return lines


def detail(result: AuditResult, repo: Path, policy: dict) -> list[str]:
    lines = [f"## {result.repo}: {len(result.open)} open, {len(result.waived)} waived", ""]
    if result.open:
        lines += ["| Severity | Check | Path | Line | Finding |", "| --- | --- | --- | ---: | --- |"]
        for f in result.open:
            lines.append(f"| {f.severity} | {f.check} | {f.path} | {f.line or ''} | {CHECKS[f.check][2]}: {f.message} |")
    if result.waived:
        waivers = (load_json(repo / policy["waivers"]["file"]) or {}).get("waivers", [])
        lines += ["", "Waived:", "", "| Severity | Check | Path | Owner | Expires | Reason |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for f in result.waived:
            w = next(w for w in waivers if w["check"] == f.check and w["path"] == f.path)
            lines.append(f"| {f.severity} | {f.check} | {f.path} | {w['owner']} | {w['expires']} | {w['reason']} |")
    lines.append("")
    return lines


def render(repos: list[Path], policy: dict, as_of: date) -> tuple[str, list[AuditResult]]:
    results = [run_audit(r, policy, as_of) for r in repos]
    out = ["# Workspace audit", "",
           f"Policy: {policy['policy_version']} · as of {as_of.isoformat()} · {len(CHECKS)} checks", ""]
    out += summary_table(results) + [""] + area_table(results) + [""]
    for res, repo in zip(results, repos):
        out += detail(res, repo, policy)
    return "\n".join(out), results


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit repositories against an accountable-workspace policy")
    ap.add_argument("repos", nargs="+", type=Path)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--as-of", default=None, help="date for waiver expiry, YYYY-MM-DD (default: today)")
    ap.add_argument("--fail-on", choices=SEVERITIES, default=None,
                    help="exit 1 if any open finding is this severe or worse")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    text, results = render(args.repos, load_policy(args.policy), as_of)
    print(text)
    if args.fail_on:
        worst = SEVERITIES.index(args.fail_on)
        if any(SEVERITIES.index(f.severity) <= worst for r in results for f in r.open):
            sys.exit(1)


if __name__ == "__main__":
    main()
