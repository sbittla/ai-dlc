"""Run the fitness rules as a gate, or measure them on the seeded cases (provided).

    python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json
    python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json --overlay ../data/seeded/V02 --gate
    python -m fitcheck.report --repo ../data/relay-repo --rules ../data/rules.json --seeded ../data/seeded

--gate exits 1 if there is any finding. --seeded runs every case in the manifest
and compares what fired with what each case expects.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graph import build_graph, load_tree
from .rules import run_rules


def check(repo, rules, overlay=None):
    files = load_tree(repo, overlay)
    graph = build_graph(files)
    return graph, run_rules(graph, files, rules)


def render_findings(findings, graph) -> str:
    edges = sum(len(v) for v in graph.values())
    lines = [f"# Fitness check: {len(graph)} modules, {edges} imports, {len(findings)} finding(s)", ""]
    if findings:
        lines += ["| Rule | ADR | Module | Line | Finding |", "| --- | --- | --- | ---: | --- |"]
        lines += [f"| {f.rule} | {f.adr} | {f.module} | {f.line} | {f.message} |" for f in findings]
        lines.append("")
    return "\n".join(lines) + "\n"


def evaluate_seeded(repo, rules, seeded_dir) -> tuple[list[dict], dict]:
    manifest = json.loads((Path(seeded_dir) / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for case in manifest:
        _, findings = check(repo, rules, Path(seeded_dir) / case["id"])
        fired = sorted({f.rule for f in findings})
        expected = sorted(case["expect"])
        if not expected:
            outcome = "clean (control)" if not fired else "false alarm"
        elif fired == expected:
            outcome = "flagged by design" if case.get("note") else "detected"
        elif not fired:
            outcome = "missed"
        else:
            outcome = "partly detected"
        rows.append({"id": case["id"], "title": case["title"], "expected": expected, "fired": fired,
                     "outcome": outcome, "why": case.get("blind_spot") or case.get("note") or ""})
    violations = [r for r in rows if r["expected"]]
    summary = {
        "cases": len(rows),
        "violations": len(violations),
        "caught": sum(r["outcome"] in ("detected", "flagged by design") for r in violations),
        "missed": sum(r["outcome"] == "missed" for r in violations),
        "controls clean": sum(r["outcome"] == "clean (control)" for r in rows),
        "false alarms": sum(r["outcome"] == "false alarm" for r in rows),
    }
    return rows, summary


def render_seeded(rows, summary, clean_findings: int) -> str:
    lines = ["# Seeded violations", "",
             "| Case | Seeded change | Expected | Fired | Outcome | Why |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['title']} | {', '.join(r['expected']) or '-'} | "
                     f"{', '.join(r['fired']) or '-'} | {r['outcome']} | {r['why']} |")
    lines += ["", f"Clean Relay 4.19.0: {clean_findings} finding(s).",
              f"Seeded violations: {summary['violations']}; caught {summary['caught']}, missed {summary['missed']}. "
              f"Controls clean: {summary['controls clean']}. False alarms: {summary['false alarms']}.", ""]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fitcheck.report")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--overlay")
    ap.add_argument("--seeded")
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    graph, findings = check(args.repo, rules, args.overlay)
    if args.seeded:
        rows, summary = evaluate_seeded(args.repo, rules, args.seeded)
        sys.stdout.write(render_seeded(rows, summary, len(findings)))
        return 0
    sys.stdout.write(render_findings(findings, graph))
    if args.gate:
        sys.stdout.write(f"gate: {'FAIL' if findings else 'PASS'}\n")
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
