"""Reports for Lab 8.1. Every number Chapter 8 quotes from this lab is printed here.

    python -m testfirst.report incident                    # the opening incident, replayed
    python -m testfirst.report grade                       # grade relay-repo's test-first files
    python -m testfirst.report grade --gate; echo $?       # exit 1 unless every grading rule passes
    python -m testfirst.report release                     # Relay 4.20.0: spec, suite, lint, changed files

Run from starter/ (your work) or solution/ (the reference). On Windows
PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .grade import MODULES_UNDER_TEST, REFERENCE, TEST_FILES, grade, load_variants
from .incident import criteria_of, replay
from .oracle import TITLES, check_files

LAB = Path(__file__).resolve().parents[2]
DATA = LAB / "data"
STUBS = LAB / "starter" / "relay-repo"


def pct(a: int, b: int) -> str:
    return f"{a / b:.1%}" if b else "-"


def report_incident(repo: Path = REFERENCE) -> str:
    """The incident always uses the reference repository's approved tests, whatever the target."""
    inc = replay(repo, DATA)
    own = inc.agent_on_agent
    passed = [r for r in own.results if r.outcome == "passed"]
    lines = ["# The opening incident, replayed", "",
             "| Measure | Result |", "| --- | ---: |",
             f"| Agent's tests passing on the agent's code | {len(passed)} of {len(own.results)} |"]
    for name, (ran, total) in inc.coverage.items():
        lines.append(f"| Line coverage of the agent's `{name}` by its tests | {ran} of {total} ({pct(ran, total)}) |")
    blocking = [f for f in inc.findings if f.blocking]
    lines.append(f"| Oracle findings on the agent's tests (blocking) | {len(inc.findings)} ({len(blocking)}) |")
    approved, ref = inc.approved_on_agent, inc.approved_on_reference
    lines.append(f"| Approved tests failing on the agent's code | {len(approved.failed())} of {len(approved.results)} |")
    lines.append(f"| Approved tests failing on the reference code | {len(ref.failed())} of {len(ref.results)} |")
    lines += ["", "## Oracle findings on the agent's tests", "", "| Code | Test | Line | Finding |",
              "| --- | --- | ---: | --- |"]
    lines += [f.row() for f in inc.findings]
    lines += ["", "## Approved tests that fail on the agent's code", "", "| Test file | Test | Checks |",
              "| --- | --- | --- |"]
    lines += [f"| {r.file} | `{r.test}` | {criteria_of(r.test, r.file)} |" for r in approved.failed()]
    by = {}
    for r in approved.failed():
        key = criteria_of(r.test, r.file)
        by[key] = by.get(key, 0) + 1
    lines += ["", "Failing approved tests by what they check: " +
              ", ".join(f"{k} {v}" for k, v in sorted(by.items()))]
    return "\n".join(lines)


def report_grade(repo: Path, groups: tuple[str, ...]) -> tuple[str, bool]:
    g = grade(repo, STUBS, DATA, groups)
    lines = ["# Test-first grade", "", "| Rule | Result |", "| --- | --- |"]
    for group in groups:
        right, total, early, wrong = g.right_reason(group)
        lines.append(f"| `{TEST_FILES[group]}`: tests written | {'yes' if g.written[group] else 'no'} |")
        lines.append(f"| ... criteria named (missing) | {', '.join(g.named[group]) or 'none missing'} |")
        lines.append(f"| ... fail on the starter stubs with NotImplementedError from src/relay | {right} of {total} |")
        if early:
            lines.append(f"| ... pass before the code exists | {', '.join(early)} |")
        if wrong:
            lines.append(f"| ... fail for another reason | {', '.join(wrong)} |")
    ref_failed = g.reference.failed()
    lines.append(f"| Pass on the reference implementation | {len(g.reference.results) - len(ref_failed)} of "
                 f"{len(g.reference.results)} |")
    killed = sum(g.killed(v, r) for v, r in g.bugs)
    lines.append(f"| Seeded bugs caught | {killed} of {len(g.bugs)} |")
    blocking = [f for f in g.findings if f.blocking]
    lines.append(f"| Oracle findings (blocking) | {len(g.findings)} ({len(blocking)}) |")
    lines += ["", "| Seeded bug | Group | Caught by | What it does |", "| --- | --- | --- | --- |"]
    for v, run in g.bugs:
        failing = [r.test for r in run.failed()]
        caught = f"{len(failing)} test(s), e.g. `{failing[0]}`" if failing else "**not caught**"
        lines.append(f"| {v['id']} | {v['group']} | {caught} | {v['description']} |")
    if g.findings:
        lines += ["", "| Code | Test | Line | Finding |", "| --- | --- | ---: | --- |"] + [f.row() for f in g.findings]
    lines += ["", f"grade: {'PASS' if g.passed else 'FAIL'}"]
    return "\n".join(lines), g.passed


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def changed_files(repo: Path) -> tuple[list[str], list[str]]:
    """(added, modified) relative to canonical 4.19.0, from data/relay-4.19.0-manifest.json."""
    base = json.loads((DATA / "relay-4.19.0-manifest.json").read_text(encoding="utf-8"))["sha256"]
    files = {p.relative_to(repo).as_posix(): p for p in repo.rglob("*") if p.is_file()
             and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}
    added = sorted(set(files) - set(base))
    modified = sorted(n for n in base if n in files and _digest(files[n]) != base[n])
    return added, modified


def spec_summary(repo: Path) -> dict:
    text = (repo / "specs" / "001-escalation-rules" / "spec.md").read_text(encoding="utf-8")
    coverage = re.findall(r"^Coverage: (\w+)$", text, re.M)
    section = text.split("\n## Data rules", 1)[1].split("\n## ", 1)[0]
    schema = json.loads((repo / "specs" / "001-escalation-rules" / "contracts" / "escalation-rules.schema.json")
                        .read_text(encoding="utf-8"))
    fields = [f"{d}.{f}" for d, body in schema["$defs"].items() for f in body["properties"]]
    classified = {line.split("|")[1].strip().strip("`") for line in section.splitlines() if line.startswith("| `")}
    tasks = (repo / "specs" / "001-escalation-rules" / "tasks.md").read_text(encoding="utf-8")
    api = json.loads((repo / "specs" / "001-escalation-rules" / "contracts" / "escalation-api.openapi.json")
                     .read_text(encoding="utf-8"))
    return {"version": re.search(r"^Version: (\S+)$", text, re.M)[1], "criteria": len(coverage),
            "full": coverage.count("full"), "partial": coverage.count("partial"),
            "constraints": len(re.findall(r"^### SEC-\d\d", text, re.M)), "definitions": len(schema["$defs"]),
            "fields": len(fields), "classified": sum(f in classified for f in fields),
            "tasks": len(re.findall(r"^### T\d\d", tasks, re.M)),
            "operations": sum(len(ops) for ops in api["paths"].values())}


def report_release(repo: Path) -> str:
    s = spec_summary(repo)
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=repo,
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    summary = (run.stdout.strip().splitlines() or ["(no output)"])[-1]
    summary = re.sub(r" in [0-9.]+s.*$", "", summary)
    collect = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                             cwd=repo, capture_output=True, text=True, timeout=600,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    per_file: dict[str, int] = {}
    for line in collect.stdout.splitlines():
        if "::" in line:
            name = line.split("::", 1)[0]
            per_file[name] = per_file.get(name, 0) + 1
    matrix = sum("test_SEC07_every_route_refuses[" in line for line in collect.stdout.splitlines())
    oracle_on_relay = check_files(sorted((repo / "tests" / "escalation").glob("test_*.py"))
                                  + sorted((repo / "tests").glob("test_service_*.py")), MODULES_UNDER_TEST)
    exempt = [f for f in oracle_on_relay if f.exempt]
    lint = subprocess.run([sys.executable, "tools/lint.py"], cwd=repo, capture_output=True, text=True)
    added, modified = changed_files(repo)
    version = re.search(r'__version__ = "([^"]+)"', (repo / "src" / "relay" / "__init__.py").read_text(
        encoding="utf-8"))[1]
    lines = ["# Relay release", "", "| Measure | Value |", "| --- | --- |",
             f"| Relay version | {version} |",
             f"| Spec | ESC-SPEC-1 {s['version']} |",
             f"| Criteria in the spec (of PRD v1.1's 31), full / partial | {s['criteria']}, {s['full']} / "
             f"{s['partial']} |",
             f"| Security constraints | {s['constraints']} |",
             f"| Contract definitions; fields classified | {s['definitions']}; {s['classified']} of {s['fields']} |",
             f"| Tasks in the plan | {s['tasks']} |",
             f"| Operations in the OpenAPI description | {s['operations']} |",
             f"| Test suite | {summary} |",
             f"| Lint | {(lint.stdout.strip().splitlines() or [''])[-1]} |",
             f"| Refusal-matrix cases (`test_SEC07_every_route_refuses`) | {matrix} |",
             f"| Oracle check on Relay's escalation and service tests: findings, blocking, exempt "
             f"(properties, reviewed markers) | {len(oracle_on_relay)}, "
             f"{sum(f.blocking for f in oracle_on_relay)}, {len(exempt)} "
             f"({sum(f.exempt == 'property' for f in exempt)}, {sum(f.exempt != 'property' for f in exempt)}) |",
             f"| Files added since 4.19.0 | {len(added)} |",
             f"| Files modified since 4.19.0 | {len(modified)} |",
             "", "| Test file | Test cases |", "| --- | ---: |"]
    lines += [f"| `{name}` | {n} |" for name, n in sorted(per_file.items())]
    lines += ["", "Added:", ""] + [f"- `{a}`" for a in added] + ["", "Modified:", ""] + [f"- `{m}`" for m in modified]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m testfirst.report", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("incident")
    g = sub.add_parser("grade")
    g.add_argument("--groups", default="hours,delivery")
    g.add_argument("--gate", action="store_true")
    sub.add_parser("release")
    sub.add_parser("variants")
    args = ap.parse_args(argv)
    repo = (Path.cwd() / "relay-repo").resolve()
    sys.path.insert(0, str(repo / "src"))
    if args.cmd == "incident":
        print(report_incident())
    elif args.cmd == "grade":
        text, passed = report_grade(repo, tuple(args.groups.split(",")))
        print(text)
        return 0 if passed or not args.gate else 1
    elif args.cmd == "release":
        print(report_release(repo))
    else:
        for v in load_variants(DATA):
            print(f"{v['id']}: {v['description']} ({', '.join(v['files'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
