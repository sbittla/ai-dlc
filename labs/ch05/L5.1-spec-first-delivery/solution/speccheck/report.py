"""Check spec packages and print the report Chapter 5 quotes.

    python -m speccheck.report --prd ../data/prd-v1.md --tests relay-repo/tests \
        --spec relay-repo/specs/001-escalation-rules [--spec DIR --tasks FILE ...] \
        [--details] [--plan] [--gate]

Each --spec is one column. A --tasks FILE checks that task list instead of the
package's own tasks.md; give "-" to keep the package's. --plan prints the task
graph and the trace matrix for the first package. --gate exits with status 1 if
any package has a blocking finding.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import plan
from .checks import Result, run_checks
from .core import CHECKS, SEVERITIES
from .repo import find_tests
from .spec import Prd, load_prd


def summary_rows(results: list[Result], prd: Prd) -> list[tuple[str, list[str]]]:
    rows = []

    def add(label, fn):
        rows.append((label, [fn(r) for r in results]))

    add("Spec version", lambda r: f"{r.spec.id} {r.spec.version}".strip() or "–")
    add("Status", lambda r: r.spec.header.get("Status", "–"))
    add(f"PRD criteria in this slice (of {len(prd.criteria)})", lambda r: str(len(r.spec.criteria)))
    add(f"PRD requirements in this slice (of {len(prd.requirements)})",
        lambda r: str(len({c.requirement for c in r.spec.criteria})))
    add("Criteria covered fully / partly",
        lambda r: f"{sum(c.coverage == 'full' for c in r.spec.criteria)} / "
                  f"{sum(c.coverage == 'partial' for c in r.spec.criteria)}")
    add("Security constraints", lambda r: str(len(r.spec.constraints)))
    add("Contract fields classified",
        lambda r: (f"{sum(f in r.spec.data_rules for f in r.contract.fields)} of {len(r.contract.fields)}"
                   if r.contract else "no contract"))
    add("Tasks", lambda r: str(len(r.tasks.tasks)))
    add("Criteria with a test of the same ID",
        lambda r: f"{len(r.spec.criteria) - sum(f.code == 'SP030' for f in r.findings)} of {len(r.spec.criteria)}")
    for sev in SEVERITIES:
        add(f"Open findings: {sev}", lambda r, s=sev: str(sum(f.severity == s for f in r.findings)))
    add("**Total open findings**", lambda r: f"**{len(r.findings)}**")
    add("Blocking findings (`--gate`)", lambda r: str(sum(f.blocking for f in r.findings)))
    add("Warnings", lambda r: str(sum(not f.blocking for f in r.findings)))
    return rows


def table(header: list[str], rows: list[list[str]], right_from: int = 1) -> list[str]:
    align = ["---"] * right_from + ["---:"] * (len(header) - right_from)
    return ["| " + " | ".join(header) + " |", "| " + " | ".join(align) + " |"] + \
           ["| " + " | ".join(r) + " |" for r in rows]


def render(results: list[Result], labels: list[str], prd: Prd, details: bool = False,
           with_plan: bool = False) -> str:
    out = ["# Spec check", "", f"PRD version {prd.version}; tests found: {len(results[0].tests)}", ""]
    out += table(["Measure"] + labels, [[label] + vals for label, vals in summary_rows(results, prd)])
    out += ["", "## Findings by check", ""]
    codes = sorted({f.code for r in results for f in r.findings})
    counts = [Counter(f.code for f in r.findings) for r in results]
    out += table(["Check"] + labels, [[f"{c} {CHECKS[c][2]}"] + [str(k[c]) for k in counts] for c in codes])
    if details:
        for label, r in zip(labels, results):
            out += ["", f"## Details: {label}", ""]
            if not r.findings:
                out.append("No open findings.")
            for f in r.findings:
                gate = "blocks" if f.blocking else "warns"
                out.append(f"- **{f.code}** ({f.severity}, {gate}) {f.item}: {f.message}")
    if with_plan:
        r = results[0]
        groups = plan.waves(r.tasks)
        out += ["", f"## Task graph: {labels[0]}", ""]
        out += [f"Wave {n}: {', '.join(g)}" for n, g in enumerate(groups, 1)]
        tiers = plan.tier_counts(r.tasks)
        out += ["", f"Tasks: {len(r.tasks.tasks)}; waves: {len(groups)}; longest chain: {len(groups)} tasks",
                "Tiers: " + ", ".join(f"{t} {n}" for t, n in sorted(tiers.items())),
                f"Tasks reading untrusted input: {', '.join(t.id for t in r.tasks.tasks if t.untrusted == 'yes') or 'none'}",
                f"High-risk tasks: {', '.join(t.id for t in r.tasks.tasks if t.risk == 'high') or 'none'}",
                "", "```mermaid", plan.mermaid(r.tasks), "```", "", "## Trace matrix", ""]
        out += table(["Requirement", "Criterion", "Tasks", "Tests"], [list(x) for x in plan.trace_rows(
            r.spec, r.tasks, r.tests)], right_from=3)
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="speccheck.report", description=__doc__.splitlines()[0])
    ap.add_argument("--prd", type=Path, required=True)
    ap.add_argument("--tests", type=Path, required=True, help="folder of tests whose names carry criterion IDs")
    ap.add_argument("--spec", type=Path, action="append", required=True)
    ap.add_argument("--tasks", action="append", default=[])
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args(argv)
    prd = load_prd(args.prd)
    tests = find_tests(args.tests)
    results, labels = [], []
    for i, spec_dir in enumerate(args.spec):
        tasks = args.tasks[i] if i < len(args.tasks) and args.tasks[i] != "-" else None
        results.append(run_checks(spec_dir, prd, tests, Path(tasks) if tasks else None))
        labels.append(Path(tasks).name if tasks else spec_dir.name)
    sys.stdout.write(render(results, labels, prd, args.details, args.plan))
    blocking = sum(f.blocking for r in results for f in r.findings)
    if args.gate:
        print(f"\nGate: {'FAIL' if blocking else 'PASS'} ({blocking} blocking finding(s))")
        return 1 if blocking else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
