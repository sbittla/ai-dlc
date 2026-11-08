"""Lab 11.2's command line. Provided; it calls your functions and prints every number the chapter quotes.

    python -m cloudmap.report mapping ../data/mapping.json
    python -m cloudmap.report mapping ../data/mapping-draft.json
    python -m cloudmap.report compare [--no-ha] [--service-hours-per-week 50]

Paths default to ../data/, relative to the folder you run from (starter/ or solution/).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compare import CATEGORIES, monthly_cost, schedule
from .mapping import check_mapping, differences_by_dimension, load

DATA = Path("../data")
PROVIDERS = ("aws", "azure", "gcp")


def render_mapping(mapping: dict, required: list[str], title: str) -> str:
    problems = check_mapping(mapping, required)
    eq = {k: sum(r["equivalence"] == k for r in mapping["rows"]) for k in ("close", "partial", "different")}
    lines = [f"# Mapping check: {title}", "",
             f"Rows: {len(mapping['rows'])} ({eq['close']} close, {eq['partial']} partial, "
             f"{eq['different']} different). Differences by dimension: " +
             ", ".join(f"{k} {v}" for k, v in differences_by_dimension(mapping).items()) + ".", ""]
    lines += [f"- {p}" for p in problems] or ["No problems found."]
    lines += ["", f"Problems: {len(problems)}."]
    return "\n".join(lines) + "\n"


def render_compare(workload: dict, tables: dict, ha: bool | None, hours_per_week: float | None) -> str:
    base = {p: monthly_cost(workload, tables[p], ha) for p in PROVIDERS}
    title = "Monthly fixed cost by provider"
    if ha is False:
        title += ", without a database standby"
    lines = [f"# {title}", "", f"Workload {workload['name']} ({workload['source']}). "
             f"Price tables dated {tables['aws']['as_of']}: {tables['aws']['status']}", "",
             "| Category | AWS | Azure | GCP |", "| --- | ---: | ---: | ---: |"]
    for c in CATEGORIES + ("total",):
        cells = " | ".join(f"{base[p][c]:,.2f}" for p in PROVIDERS)
        lines.append(f"| {'**total**' if c == 'total' else c} | {cells} |")
    order = sorted(PROVIDERS, key=lambda p: base[p]["total"])
    lines += ["", "Under these assumptions: " + ", ".join(f"{p} ${base[p]['total']:,.2f}" for p in order) + "."]
    for p in PROVIDERS:
        big = max(CATEGORIES, key=lambda c: base[p][c])
        lines.append(f"Largest category on {p}: {big}, {100 * base[p][big] / base[p]['total']:.1f}% of its total.")
    if hours_per_week is not None:
        sched = {p: monthly_cost(schedule(workload, hours_per_week), tables[p], ha) for p in PROVIDERS}
        lines += ["", f"With the service containers running {hours_per_week:g} hours a week:"]
        for p in PROVIDERS:
            saved = base[p]["total"] - sched[p]["total"]
            lines.append(f"- {p}: ${sched[p]['total']:,.2f} a month, saving ${saved:,.2f} "
                         f"({100 * saved / base[p]['total']:.1f}%).")
    lines += ["", f"Not compared: {workload['not_compared']}."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cloudmap.report", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mapping")
    m.add_argument("file")
    m.add_argument("--required", default=str(DATA / "required-concerns.json"))
    c = sub.add_parser("compare")
    c.add_argument("--workload", default=str(DATA / "workload.json"))
    c.add_argument("--prices", default=str(DATA / "prices"))
    c.add_argument("--no-ha", action="store_true")
    c.add_argument("--service-hours-per-week", type=float)
    args = ap.parse_args(argv)
    if args.cmd == "mapping":
        out = render_mapping(load(args.file), load(args.required)["concerns"], Path(args.file).name)
    else:
        tables = {p: load(Path(args.prices) / f"{p}-2026-11.json") for p in PROVIDERS}
        out = render_compare(load(args.workload), tables, False if args.no_ha else None, args.service_hours_per_week)
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
