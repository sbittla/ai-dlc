"""Relay's security gate over scanner reports (4.29.0; ADR-029 and ADR-044), standard library only.

    python tools/security_gate.py --policy security/gates.json --require-reports semgrep.sarif gitleaks.sarif ...

It decides one change at the `ci` stage of security/gates.json (relay-security-gates-v1), as Lab 13.1's
reference `decide()` does, with the report checks Lab 15.1's scan stage adds. Exit codes are the policy's own:

    0  pass
    1  blocked: a finding that is not validly suppressed comes from an always_block scanner (gitleaks, depgate) or
       has a security-severity at or above block_at_or_above (7.0)
    2  cannot check: with --require-reports, a report that is missing, unreadable, not SARIF 2.1.0, has no runs, or
       is not written by one of the stage's scanners; or a stage scanner (other than depgate) with no report

Without --require-reports, a report that is missing or has no runs is listed and skipped (4.28.0's behaviour,
the March incident); every workflow from 4.29.0 passes the flag.

A suppression in the policy's suppressions file applies to one rule at one fingerprint (the SARIF
`partialFingerprints.primaryLocationLineHash`). It needs a reason, a reviewer on the policy's list who is not
its author, an expiry not passed and at most max_days after its creation; never for a never_suppressible scanner.
A result's severity is its `security-severity` property, else its rule's, else 8.0 for level "error" and 4.0
otherwise. The scanner is the report's tool name, compared without regard to case.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PASS, BLOCKED, CANNOT_CHECK = 0, 1, 2
STAGE = "ci"


@dataclass(frozen=True)
class Finding:
    scanner: str
    rule: str
    severity: float
    path: str
    line: int
    fingerprint: str
    message: str


def _severity(result: dict, rules: dict) -> float:
    for props in (result.get("properties") or {}, (rules.get(result.get("ruleId")) or {}).get("properties") or {}):
        if "security-severity" in props:
            return float(props["security-severity"])
    return 8.0 if result.get("level") == "error" else 4.0


def read_report(path: Path, scanners: set[str]) -> tuple[list[Finding], set[str], str | None]:
    """(findings, scanners that wrote the report, problem). A problem means the report cannot be used."""
    if not path.is_file():
        return [], set(), "missing"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], set(), "not readable JSON"
    if not isinstance(doc, dict) or doc.get("version") != "2.1.0":
        return [], set(), "not SARIF 2.1.0"
    runs = doc.get("runs")
    if not runs:
        return [], set(), "no runs: an empty report is not a clean one"
    out, names = [], set()
    for run in runs:
        driver = (run.get("tool") or {}).get("driver") or {}
        scanner = str(driver.get("name", "")).lower()
        if scanner not in scanners:
            return [], set(), f"written by {driver.get('name')!r}, not one of the stage's scanners"
        names.add(scanner)
        rules = {r.get("id"): r for r in driver.get("rules") or []}
        for r in run.get("results") or []:
            loc = ((r.get("locations") or [{}])[0].get("physicalLocation")) or {}
            out.append(Finding(scanner, str(r.get("ruleId")), _severity(r, rules),
                               (loc.get("artifactLocation") or {}).get("uri", ""),
                               (loc.get("region") or {}).get("startLine", 0),
                               (r.get("partialFingerprints") or {}).get("primaryLocationLineHash", ""),
                               (r.get("message") or {}).get("text", "")))
    return out, names, None


def suppression_problem(sup: dict, policy: dict, as_of: date) -> str | None:
    """Why a suppression may not be applied, or None if it is valid."""
    rules = policy["suppressions"]
    if not sup.get("reason", "").strip():
        return "no reason"
    if sup.get("reviewed_by") not in rules["reviewers"]:
        return f"reviewer {sup.get('reviewed_by')!r} is not a person on the policy's list"
    if sup["reviewed_by"] == sup.get("author"):
        return "reviewed by its own author"
    created, expires = date.fromisoformat(sup["created"]), date.fromisoformat(sup["expires"])
    if expires < as_of:
        return f"expired on {sup['expires']}"
    if expires - created > timedelta(days=rules["max_days"]):
        return f"longer than {rules['max_days']} days"
    return None


def decide(findings: list[Finding], policy: dict, suppressions: list[dict], as_of: date) -> tuple[list, list, list]:
    """(blocking, warnings, notes) for the stage's findings."""
    scanners = set(policy["stages"][STAGE]["scanners"])
    blocking, warnings, notes = [], [], []
    by_key: dict = {}
    for sup in suppressions:
        by_key.setdefault((sup["rule"], sup["fingerprint"]), []).append(sup)
    for f in findings:
        if f.scanner not in scanners:
            continue
        applied = None
        for sup in by_key.get((f.rule, f.fingerprint), []):
            problem = ("this scanner's findings cannot be suppressed"
                       if f.scanner in policy["suppressions"]["never_suppressible"]
                       else suppression_problem(sup, policy, as_of))
            if problem is None:
                applied = sup["id"]
                break
            note = f"suppression {sup['id']} ignored: {problem}"
            if note not in notes:
                notes.append(note)
        if applied:
            notes.append(f"suppressed by {applied}: {f.scanner} {f.rule} {f.path}:{f.line}")
        elif f.scanner in policy["always_block"] or f.severity >= policy["block_at_or_above"]:
            blocking.append(f)
        else:
            warnings.append(f)
    return blocking, warnings, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="security_gate.py", description="relay-security-gates-v1 over SARIF reports.")
    ap.add_argument("--policy", required=True)
    ap.add_argument("--require-reports", action="store_true")
    ap.add_argument("--suppressions", help="default: the policy's suppressions file, from the repository root")
    ap.add_argument("--as-of", help="YYYY-MM-DD for suppression expiry (default: today, UTC)")
    ap.add_argument("reports", nargs="+")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    policy_path = Path(args.policy)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    sup_path = Path(args.suppressions) if args.suppressions else \
        policy_path.resolve().parent.parent / policy["suppressions"]["file"]
    suppressions = json.loads(sup_path.read_text(encoding="utf-8")).get("suppressions", [])
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(timezone.utc).date()
    scanners = set(policy["stages"][STAGE]["scanners"])

    findings, present, problems = [], set(), []
    for name in args.reports:
        got, names, problem = read_report(Path(name), scanners)
        if problem:
            problems.append(f"{name}: {problem}")
        findings += got
        present |= names
    missing = sorted(s for s in scanners - {"depgate"} if s not in present)
    blocking, warnings, notes = decide(findings, policy, suppressions, as_of)

    out = sys.stdout
    for f in blocking:
        out.write(f"BLOCK {f.scanner} {f.rule} ({f.severity}) {f.path}:{f.line}: {f.message}\n")
    for f in warnings:
        out.write(f"warn  {f.scanner} {f.rule} ({f.severity}) {f.path}:{f.line}: {f.message}\n")
    for n in notes:
        out.write(f"note  {n}\n")
    for p in problems:
        out.write(f"{'CANNOT CHECK' if args.require_reports else 'skipped'} {p}\n")
    if args.require_reports and missing:
        out.write("CANNOT CHECK no report from: " + ", ".join(missing) + "\n")
    if args.require_reports and (problems or missing):
        status = CANNOT_CHECK
    else:
        status = BLOCKED if blocking else PASS
    out.write(f"security gate ({policy.get('policy')}, {STAGE}): exit {status} "
              f"({policy.get('exit_codes', {}).get(str(status), '')})\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
