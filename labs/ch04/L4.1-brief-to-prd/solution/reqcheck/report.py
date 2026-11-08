"""Check one or more PRDs and print a Markdown comparison (provided).

    python -m reqcheck.report --sources ../data/sources --lexicon ../data/lexicon.json \\
        ../data/prd-draft.md ../data/prd-v1.md

Options:
    --details        every finding, one per line, for each PRD
    --matrix         the traceability matrix of the last PRD
    --impact ID      what to re-review in the last PRD if ID (a source, goal,
                     decision or requirement) changes
    --gate           Relay's CI gate: exit with status 1 if the last PRD has an
                     open finding from a blocking check (core.BLOCKING); findings
                     from word-list checks (core.WARNING) are printed as warnings
    --fail-on SEV    stricter: exit 1 on any open finding at SEV or above
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import prd as prdmod
from . import trace
from .checks import GWT, check_provenance, run_checks
from .core import AREAS, BLOCKING, CHECKS, SEVERITIES, load_lexicon
from .sources import load_sources


def summary(p: prdmod.PRD, sources, lexicon) -> dict:
    result = run_checks(p, sources, lexicon)
    refs = [(g.id, s) for g in p.goals for s in g.sources] + [(r.id, s) for r in p.requirements for s in r.sources]
    verbatim = sum(1 for item, s in refs
                   if not [f for f in check_provenance(item, [s], sources, 0) if f.code in ("RQ002", "RQ003")])
    criteria = [c for r in p.requirements for c in r.criteria]
    covered = {r.category for r in p.requirements if r.kind == "nfr"} & set(lexicon.required_nfr_categories)
    comp = trace.completeness(p)
    return {
        "prd": p, "result": result, "refs": len(refs), "verbatim": verbatim,
        "criteria": len(criteria), "gwt": sum(1 for c in criteria if GWT.match(c.text)),
        "functional": sum(r.kind == "functional" for r in p.requirements),
        "nfr": sum(r.kind == "nfr" for r in p.requirements),
        "covered": len(covered), "completeness": comp,
    }


def render(paths: list[Path], sources, lexicon) -> tuple[str, list[dict]]:
    sums = [summary(prdmod.load(path), sources, lexicon) for path in paths]
    flags = sums[0]["result"].flags if sums else ()
    lines = [f"Lexicon: `{lexicon.version}` · sources: {len(sources)} documents "
             f"({', '.join(sorted(sources))})", "",
             f"Flagged source blocks (instruction-like text): {len(flags)}"]
    for f in flags:
        first = f.text.split("\n")[0][:70]
        lines.append(f"- {f.doc} lines {f.first_line}-{f.last_line}: {first!r}")
    names = [path.name for path in paths]
    head = "| {} | " + " | ".join(names) + " |"
    rule = "| --- | " + " | ".join("---:" for _ in names) + " |"

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(s) for s in sums) + " |")

    lines += ["", head.format("PRD"), rule]
    row("Version", lambda s: s["prd"].version)
    row("Status", lambda s: s["prd"].status)
    row("Goals", lambda s: str(len(s["prd"].goals)))
    row("Decisions recorded", lambda s: str(len(s["prd"].decisions)))
    row("Requirements (functional + NFR)", lambda s: f"{s['functional'] + s['nfr']} ({s['functional']} + {s['nfr']})")
    row("Acceptance criteria", lambda s: str(s["criteria"]))
    row("Criteria in Given/When/Then form", lambda s: f"{s['gwt']} of {s['criteria']}")
    row("Source quotes found verbatim", lambda s: f"{s['verbatim']} of {s['refs']}")
    row(f"Required NFR categories covered (of {len(lexicon.required_nfr_categories)})", lambda s: str(s["covered"]))
    row("Requirements with goal, source and test",
        lambda s: f"{s['completeness'].complete} of {s['completeness'].requirements} ({s['completeness'].share:.1%})")

    counts = [Counter(f.severity for f in s["result"].findings) for s in sums]
    lines += ["", head.format("Open findings by severity"), rule]
    for sev in SEVERITIES:
        lines.append(f"| {sev} | " + " | ".join(str(c[sev]) for c in counts) + " |")
    lines.append("| **Total open** | " + " | ".join(f"**{len(s['result'].findings)}**" for s in sums) + " |")
    lines.append("| Blocking (gate) | " + " | ".join(
        str(sum(f.code in BLOCKING for f in s["result"].findings)) for s in sums) + " |")
    lines.append("| Warnings | " + " | ".join(
        str(sum(f.code not in BLOCKING for f in s["result"].findings)) for s in sums) + " |")

    areas = [Counter(f.area for f in s["result"].findings) for s in sums]
    lines += ["", head.format("Open findings by area"), rule]
    for area in AREAS:
        lines.append(f"| {area} | " + " | ".join(str(c[area]) for c in areas) + " |")

    codes = [Counter(f.code for f in s["result"].findings) for s in sums]
    used = sorted({code for c in codes for code in c})
    lines += ["", head.format("Open findings by check"), rule]
    for code in used:
        kind = "blocks" if code in BLOCKING else "warns"
        lines.append(f"| {code} {CHECKS[code][2]} ({CHECKS[code][0]}; {kind}) | " + " | ".join(str(c[code]) for c in codes) + " |")
    return "\n".join(lines), sums


def render_details(s: dict, name: str) -> str:
    lines = [f"### Findings: {name}", ""]
    lines += [f"- {f.line()}" for f in s["result"].findings] or ["- none"]
    return "\n".join(lines)


def render_matrix(p: prdmod.PRD) -> str:
    lines = ["| Goal | Requirement | Decisions | Sources | Tasks | Tests |", "| --- | --- | --- | --- | --- | --- |"]
    for r in trace.trace_matrix(p):
        lines.append(f"| {r.goal or '(none)'} | {r.requirement} | {', '.join(r.decisions) or '-'} | "
                     f"{', '.join(r.sources) or '(none)'} | planned in Chapter 5 | {', '.join(r.tests) or '(none)'} |")
    return "\n".join(lines)


def render_impact(p: prdmod.PRD, changed: str) -> str:
    imp = trace.impact(p, changed)
    return (f"Impact of a change to {changed}: {len(imp.direct)} requirements cite it directly "
            f"({', '.join(imp.direct) or 'none'}); {len(imp.indirect)} more depend on them "
            f"({', '.join(imp.indirect) or 'none'}); {len(imp.tests)} tests to re-review "
            f"({', '.join(imp.tests) or 'none'}).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relay requirements checker")
    ap.add_argument("prds", nargs="+", type=Path)
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--lexicon", type=Path, required=True)
    ap.add_argument("--details", action="store_true")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--impact")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fail-on", choices=SEVERITIES)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page

    sources, lexicon = load_sources(args.sources), load_lexicon(args.lexicon)
    text, sums = render(args.prds, sources, lexicon)
    print(text)
    if args.details:
        for path, s in zip(args.prds, sums):
            print("\n" + render_details(s, path.name))
    last = sums[-1]
    if args.matrix:
        print("\n" + render_matrix(last["prd"]))
    if args.impact:
        print("\n" + render_impact(last["prd"], args.impact))
    if args.gate and any(f.code in BLOCKING for f in last["result"].findings):
        return 1
    if args.fail_on:
        limit = SEVERITIES.index(args.fail_on)
        if any(SEVERITIES.index(f.severity) <= limit for f in last["result"].findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
