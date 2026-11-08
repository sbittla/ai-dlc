"""Reports for Lab 6.1 (provided). Every number the chapter quotes is printed here.

    python -m archscore.report score --drivers ../data/drivers.json ../data/options/*.json [--details]
    python -m archscore.report score ... --scenario ../data/scenarios/five-teams.json
    python -m archscore.report score ... --explain availability
    python -m archscore.report adr --drivers ../data/drivers.json ADR.md ... [--gate]
    python -m archscore.report threats --options ../data/options TM.md ... [--gate]

With --gate, the exit status is 1 if any ADR or threat model has a finding.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import structure
from .checks import CATALOGUE, check_adr, check_threat_model
from .docs import load_adr, load_threat_model
from .model import apply_scenario, load_catalogue, load_options
from .scoring import head_to_head, rank, weight_to_flip, weighted_score

PER_COMPONENT = 0.999


def fmt_pct(x: float, places: int = 1) -> str:
    return f"{100 * x:.{places}f}%"


def render_scores(catalogue, options, details=False, scenario=None) -> str:
    drivers = catalogue.drivers
    by_id = {o.id: o for o in options}
    lines = [f"# Architecture options scored against {catalogue.version} (scored by {catalogue.scored_by})", ""]
    if scenario:
        lines += [f"Scenario **{scenario['name']}**: {scenario['description']}", ""]
    head = "| Driver | Category | Weight | Must | " + " | ".join(f"{o.id} score (weighted)" for o in options) + " |"
    lines += [head, "| --- | --- | ---: | :---: | " + " | ".join("---:" for _ in options) + " |"]
    for d in drivers:
        if d.weight <= 0:
            continue
        cells = [f"{o.scores[d.id].value} ({d.weight * o.scores[d.id].value})" for o in options]
        lines.append(f"| {d.id} {d.title} | {d.category} | {d.weight} | {'yes' if d.must else ''} | "
                     + " | ".join(cells) + " |")
    totals = {o.id: weighted_score(o, drivers) for o in options}
    lines.append("| **Weighted total** | | | | " + " | ".join(
        f"**{totals[o.id].total} of {totals[o.id].maximum} ({totals[o.id].percent:.1f}%)**" for o in options) + " |")
    lines += ["", "Not architecture-significant (weight 0, listed, not scored): "
              + ", ".join(f"{d.id} ({d.note})" for d in drivers if d.weight <= 0), ""]

    ranked = rank(options, drivers)
    lines += ["## Ranking", ""]
    for n, r in enumerate(ranked, 1):
        dq = f"; disqualified on {', '.join(r.disqualified)}" if r.disqualified else ""
        lines.append(f"{n}. Option {r.option_id} — {by_id[r.option_id].name}: {r.total.total} of "
                     f"{r.total.maximum} ({r.total.percent:.1f}%), {r.deployables} deployable unit(s){dq}")
    if len(ranked) >= 2:
        lead, second = by_id[ranked[0].option_id], by_id[ranked[1].option_id]
        gap = ranked[0].total.total - ranked[1].total.total
        h2h = head_to_head(lead, second, drivers)
        lines += ["", f"Gap: {gap} points. Option {lead.id} scores higher on {len(h2h[lead.id])} drivers, "
                  f"Option {second.id} on {len(h2h[second.id])} ({', '.join(h2h[second.id]) or 'none'}), "
                  f"equal on {len(h2h['equal'])} ({', '.join(h2h['equal']) or 'none'}).", ""]
        flips = weight_to_flip(lead, second, drivers)
        flipping = {k: v for k, v in flips.items() if v is not None}
        lines.append("## Sensitivity: one weight at a time, 0 to 5")
        lines.append("")
        if flipping:
            for k, v in flipping.items():
                lines.append(f"- {k}: weight {v} would make Option {second.id} win")
        else:
            lines.append(f"- No single weight from 0 to 5 makes Option {second.id} win.")
        best = max((d for d in drivers if d.id in second.scores and d.id in lead.scores),
                   key=lambda d: second.scores[d.id].value - lead.scores[d.id].value)
        diff = second.scores[best.id].value - lead.scores[best.id].value
        if diff > 0:
            need = gap // diff + 1
            lines.append(f"- Nearest: {best.id}, where Option {second.id} leads by {diff}; its weight would have "
                         f"to rise by {need}, from {best.weight} to {best.weight + need}.")
        lines.append("")

    lines += ["## Structure (counted from each option's components and flows)", "",
              "| Measure | " + " | ".join(f"Option {o.id}" for o in options) + " |",
              "| --- | " + " | ".join("---:" for _ in options) + " |"]
    mets = {o.id: structure.metrics(o, PER_COMPONENT) for o in options}
    for key in mets[options[0].id]:
        def cell(v):
            if key == "step-path availability":
                return fmt_pct(v, 2)
            if isinstance(v, float):
                return f"{v:.1f}"
            return str(v)
        lines.append(f"| {key} | " + " | ".join(cell(mets[o.id][key]) for o in options) + " |")
    lines += ["", f"Availability assumes {fmt_pct(PER_COMPONENT)} per internal component, independent failures, "
              "and counts only the components a step needs (Equation 6.1).", ""]

    if details:
        lines += ["## Reasons", ""]
        for d in drivers:
            if d.weight <= 0:
                continue
            lines.append(f"**{d.id}** {d.title} (weight {d.weight}; source: {d.source})")
            for o in options:
                lines.append(f"- {o.id} = {o.scores[d.id].value}: {o.scores[d.id].why}")
            lines.append("")
    return "\n".join(lines) + "\n"


def render_availability(options) -> str:
    lines = ["# Equation 6.1: availability of components in series", "",
             "A_path = a1 x a2 x ... x an, assuming independent failures", ""]
    for o in options:
        n, avail = structure.path_availability(o, PER_COMPONENT)
        lines.append(f"- Option {o.id}: {n} components at {fmt_pct(PER_COMPONENT)} -> {fmt_pct(avail, 2)} "
                     f"({avail:.6f}); down {structure.unavailable_minutes(avail):.1f} minutes per 30 days")
    single = structure.unavailable_minutes(PER_COMPONENT)
    lines += ["", f"- One component at {fmt_pct(PER_COMPONENT)}: down {single:.1f} minutes per 30 days"]
    return "\n".join(lines) + "\n"


def render_findings(title: str, results: list[tuple[str, list]]) -> tuple[str, int]:
    lines = [f"# {title}", "", "| Document | Findings |", "| --- | ---: |"]
    total = 0
    for name, findings in results:
        lines.append(f"| {name} | {len(findings)} |")
        total += len(findings)
    lines.append("")
    for name, findings in results:
        if findings:
            lines += [f"## {name}", ""]
            for f in findings:
                lines.append(f"- {f.code} {f.item}: {f.message} — {CATALOGUE[f.code]}")
            lines.append("")
    return "\n".join(lines) + "\n", total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m archscore.report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--drivers", required=True)
    s.add_argument("options", nargs="+")
    s.add_argument("--details", action="store_true")
    s.add_argument("--scenario")
    s.add_argument("--explain", choices=["availability"])
    a = sub.add_parser("adr")
    a.add_argument("--drivers", required=True)
    a.add_argument("adrs", nargs="+")
    a.add_argument("--gate", action="store_true")
    t = sub.add_parser("threats")
    t.add_argument("--options", required=True, help="folder of option JSON files")
    t.add_argument("models", nargs="+")
    t.add_argument("--gate", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # em dashes print the same on every platform

    if args.cmd == "score":
        catalogue, options = load_catalogue(args.drivers), load_options(args.options)
        if args.explain == "availability":
            sys.stdout.write(render_availability(options))
            return 0
        scenario = None
        if args.scenario:
            catalogue, options, scenario = apply_scenario(catalogue, options, args.scenario)
        sys.stdout.write(render_scores(catalogue, options, args.details, scenario))
        return 0
    if args.cmd == "adr":
        catalogue = load_catalogue(args.drivers)
        results = [(Path(p).name, check_adr(load_adr(p), catalogue)) for p in args.adrs]
        text, total = render_findings("Decision records", results)
    else:
        options = {o.id: o for o in load_options(sorted(Path(args.options).glob("*.json")))}
        results = []
        for p in args.models:
            tm = load_threat_model(p)
            results.append((Path(p).name, check_threat_model(tm, options[tm.fields.get("Option", "")])))
        text, total = render_findings("Threat models", results)
    sys.stdout.write(text)
    if args.gate:
        sys.stdout.write(f"gate: {'FAIL' if total else 'PASS'} ({total} finding(s))\n")
        return 1 if total else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
