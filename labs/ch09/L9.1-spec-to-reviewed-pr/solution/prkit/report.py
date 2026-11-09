"""Lab 9.1's reports (provided).

    python -m prkit.report incident     # the check on the opening incident's 4,067-line pull request
    python -m prkit.report claims       # the simulated agent's impact-analysis claims, checked against 4.21.0
    python -m prkit.report series       # Relay 4.22.0's pull requests, measured and checked
    python -m prkit.report release      # Relay 4.22.0's test counts, from pytest's own collection
    python -m prkit.report live-review --pr PR-5    # optional, gated: a Claude model reviews one pull request

Run from starter/ or solution/. Every report reads data/ and the reference
repository in solution/relay-repo unless --repo says otherwise; the checks
themselves (prcheck, claims) come from the folder you run in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from . import codeowners, prcheck, series
from .claims import verify_all

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
REFERENCE = LAB / "solution" / "relay-repo"
NEW_TEST_FILES = ("tests/escalation/test_escalation_migrations.py", "tests/escalation/test_escalation_notices.py",
                  "tests/escalation/test_escalation_deletion.py", "tests/test_service_rule_deletion.py",
                  "tests/test_worker_escalation.py", "tests/notify/test_notify_characterization.py",
                  "tests/notify/test_notify_decide.py", "tests/notify/test_notify_migration.py",
                  "tests/notify/test_notify_compat.py")


def _findings_line(findings) -> str:
    return ", ".join(f.code for f in findings) or "none"


def report_incident(data: Path = DATA) -> str:
    record = json.loads((data / "incident-pr.json").read_text(encoding="utf-8"))
    code, total = prcheck.sizes(record)
    changes = prcheck.all_changes(record)
    minutes = record["review"]["minutes"]
    existing_tests = sorted(c.path for c in changes if prcheck.is_test(c.path) and c.status != "A")
    findings = prcheck.check_pr(record)
    lines = [f"# Pull request {record['id']}: {record['title']}", "",
             "| Measure | Value |", "| --- | ---: |",
             f"| Files changed | {len(changes)} |",
             f"| Lines added | {sum(c.added for c in changes):,} |",
             f"| Lines removed | {sum(c.removed for c in changes):,} |",
             f"| Changed lines in all | {total:,} |",
             f"| Changed lines outside tests/ | {code:,} |",
             f"| Commits | {len(record['commits'])} |",
             f"| Existing test files changed | {len(existing_tests)} |",
             f"| Review time (minutes) | {minutes} |",
             f"| Changed lines per minute of review | {round(total / minutes):,} |",
             f"| Blocking findings | {sum(f.blocking for f in findings)} |",
             f"| Warnings | {sum(not f.blocking for f in findings)} |", "",
             "## Findings", "", "| Code | Blocking | Finding |", "| --- | --- | --- |"]
    lines += [f"| {f.code} | {'yes' if f.blocking else 'no'} | {f.message} |" for f in findings]
    return "\n".join(lines)


def report_claims(data: Path = DATA) -> str:
    results = verify_all(data / "relay-4.21.0", data / "agent-claims.json")
    held = sum(v.holds for _, v in results)
    lines = ["# The agent's claims, checked against Relay 4.21.0 (the agent is simulated)", "",
             f"Claims: {len(results)}; hold: {held}; do not hold: {len(results) - held}", "",
             "| Claim | Kind | Holds | Evidence |", "| --- | --- | --- | --- |"]
    for claim, v in results:
        lines.append(f"| {claim['id']} | {claim['kind']} | {'yes' if v.holds else 'no'} | {'; '.join(v.evidence)} |")
    return "\n".join(lines)


def report_series(data: Path = DATA, repo: Path = REFERENCE) -> str:
    records = series.records(data, repo)
    lines = ["# Relay 4.22.0: the pull requests", "",
             "| PR | Task | Merged | Opened by | Reviewers | Files | Outside tests/ | In all | Review (min) | "
             "Lines per hour | Code owners at base | Blocking | Warnings |",
             "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    blocking = 0
    for r in records:
        code, total = prcheck.sizes(r)
        found = prcheck.check_pr(r)
        blocking += sum(f.blocking for f in found)
        minutes = r["review"]["minutes"]
        owners = "; ".join(prcheck.required_owners(r, codeowners.parse(r["codeowners"])))
        lines.append(f"| {r['id']} | {r['task'] or '-'} | {r['merged']} | {r['opened_by']} | "
                     f"{', '.join(r['review']['reviewers'])} | {len(prcheck.all_changes(r))} | {code} | {total} | "
                     f"{minutes} | {round(total / (minutes / 60))} | {owners} | "
                     f"{_findings_line([f for f in found if f.blocking])} | "
                     f"{_findings_line([f for f in found if not f.blocking])} |")
    totals = [prcheck.sizes(r) for r in records]
    lines += ["", f"Pull requests: {len(records)}; blocking findings: {blocking}; "
                  f"changed lines: {sum(t for _, t in totals)} ({sum(c for c, _ in totals)} outside tests/); "
                  f"largest: {max(t for _, t in totals)}", ""]
    for group, files, changed in series.grouped(data, repo):
        lines.append(f"Group {group['id']}: {files} files, {changed} changed lines ({group['title']})")
    missing = series.unassigned(data, repo)
    lines.append(f"Changed files not assigned to a pull request or group: {len(missing)}"
                 + ("" if not missing else " (" + ", ".join(missing) + ")"))
    return "\n".join(lines)


def collect(repo: Path) -> Counter:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=repo, capture_output=True, text=True, encoding="utf-8")
    ids = [line.split("::")[0].replace("\\", "/") for line in out.stdout.splitlines() if "::" in line]
    if not ids:
        raise RuntimeError("pytest collected nothing:\n" + out.stdout + out.stderr)
    return Counter(ids)


def report_release(repo: Path = REFERENCE) -> str:
    counts = collect(repo)
    lines = ["# Relay 4.22.0: tests", "", "| Test file | Tests |", "| --- | ---: |"]
    lines += [f"| `{name}` | {counts[name]} |" for name in NEW_TEST_FILES]
    lines += [f"| New in 4.22.0 | {sum(counts[n] for n in NEW_TEST_FILES)} |",
              f"| **All** | **{sum(counts.values())}** |"]
    return "\n".join(lines)


def live_review(pr_id: str, data: Path = DATA, repo: Path = REFERENCE) -> str:
    from .live import ClaudeReviewer

    [record] = [r for r in series.records(data, repo) if r["id"] == pr_id]
    diff = "\n".join(f"--- {f['path']}\n" + "\n".join("+" + x for x in f["added_lines"])
                     + "\n" + "\n".join("-" + x for x in f["removed_lines"])
                     for c in record["commits"] for f in c["files"])
    checklist = (LAB / "templates" / "review-checklist.md").read_text(encoding="utf-8")
    review = ClaudeReviewer().review(checklist, diff)
    return (f"# Live review of {pr_id} by {ClaudeReviewer().model} (stop: {review.stop_reason}; "
            f"tokens in {review.input_tokens}, out {review.output_tokens})\n\n{review.text}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m prkit.report")
    ap.add_argument("report", choices=["incident", "claims", "series", "release", "live-review"])
    ap.add_argument("--repo", type=Path, default=REFERENCE)
    ap.add_argument("--pr", default="PR-5")
    args = ap.parse_args(argv)
    if args.report == "incident":
        out = report_incident()
    elif args.report == "claims":
        out = report_claims()
    elif args.report == "series":
        out = report_series(DATA, args.repo)
    elif args.report == "release":
        out = report_release(args.repo)
    else:
        out = live_review(args.pr, DATA, args.repo)
    sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
