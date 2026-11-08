"""Lab 11.1's command line. Provided; it calls your functions and prints every number the chapter quotes.

    python -m cloudcheck.report check ../data/plans/relay-nonprod.plan.json [--overlay O] [--gate]
    python -m cloudcheck.report cost ../data/plans/relay-nonprod.plan.json [--hours H] [--budget USD]
    python -m cloudcheck.report seeded ../data/plans/relay-nonprod.plan.json --seeded ../data/seeded
    python -m cloudcheck.report teardown --apply-plan A --destroy-plan D [--inventory I] [--gate]
    python -m cloudcheck.report incident ../data/incident.json

Defaults: --policy ../data/policy.json, --prices ../data/prices/aws-us-east-1-2026-11.json and
--as-of 2026-11-30, all relative to the folder you run from (starter/ or solution/).
Exit status with --gate: 0 pass, 1 a failing finding, 2 nothing failing but something unknown.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from .cost import CATEGORIES, estimate, hours_to_threshold
from .plan import load_json, load_plan, resources, variable
from .policy import gate_status, run_policy
from .teardown import TEARDOWN_RULES, check_teardown, ready

HERE = Path.cwd()
DEFAULT_POLICY = "../data/policy.json"
DEFAULT_PRICES = "../data/prices/aws-us-east-1-2026-11.json"


def money(x: float) -> str:
    return f"${x:,.2f}"


def findings_table(findings) -> list[str]:
    lines = ["| Rule | Resource | Status | Finding |", "| --- | --- | --- | --- |"]
    lines += [f"| {f.rule} | `{f.address}` | {f.status} | {f.message} |" for f in findings]
    return lines


def summary_line(findings) -> str:
    c = Counter(f.status for f in findings)
    return (f"Findings: {c['fail']} failing, {c['cannot check']} cannot check, {c['waived']} waived. "
            f"Gate exit status: {gate_status(findings)}.")


def render_check(plan: dict, policy: dict, as_of: date, title: str) -> tuple[str, int]:
    findings = run_policy(plan, policy, as_of)
    n = len(resources(plan))
    by_rule = Counter(f.rule for f in findings if f.status == "fail")
    lines = [f"# Policy check: {title}", "",
             f"Policy {policy['policy_version']}, as of {as_of.isoformat()}. Resources checked: {n}.", ""]
    lines += findings_table(findings) if findings else ["No findings."]
    lines += ["", summary_line(findings)]
    if by_rule:
        lines.append("Failing by rule: " + ", ".join(f"{k} {v}" for k, v in sorted(by_rule.items())) + ".")
    return "\n".join(lines) + "\n", gate_status(findings)


def render_cost(plan: dict, prices: dict, title: str, hours: float | None, budget: float | None,
                details: bool) -> str:
    est = estimate(plan, prices)
    lines = [f"# Cost estimate: {title}", "",
             f"Price table {prices['price_table']} ({prices['region']}, as of {prices['as_of']}). "
             f"{prices['status']}", ""]
    if details:
        lines += ["| Resource | Category | $/hour | Basis |", "| --- | --- | ---: | --- |"]
        lines += [f"| `{x.address}` | {x.category} | {x.hourly:.4f} | {x.basis} |" for x in est.lines]
        lines.append("")
    cats = est.by_category()
    lines += ["| Category | $/hour | $/month | Share |", "| --- | ---: | ---: | ---: |"]
    for c in CATEGORIES:
        if cats[c]:
            lines.append(f"| {c} | {cats[c]:.4f} | {cats[c] * est.hours_per_month:,.2f} | "
                         f"{100 * cats[c] / est.hourly:.1f}% |")
    lines.append(f"| **total** | **{est.hourly:.4f}** | **{est.monthly:,.2f}** | 100.0% |")
    lines += ["", f"Fixed cost: {money(est.hourly)} per hour, {money(est.monthly)} per month "
                  f"({est.hours_per_month} hours), before any usage-based charges."]
    endpoints = sum(x.hourly for x in est.lines if x.address.startswith("aws_vpc_endpoint."))
    if endpoints:
        lines.append(f"Interface endpoints: {money(endpoints)} per hour, "
                     f"{100 * endpoints / est.hourly:.1f}% of the fixed cost.")
    if hours is not None:
        lines.append(f"Running for {hours:g} hours: {money(est.hourly * hours)}.")
    if budget is not None:
        marks = ", ".join(f"{p}% after {hours_to_threshold(est.hourly, budget, p):.1f} h" for p in (50, 80, 100))
        lines.append(f"Against a {money(budget)} budget, spend crosses {marks}.")
    if est.usage:
        lines += ["", "Usage-based, not estimated: " +
                  "; ".join(f"`{a}` ({what})" for a, what in est.usage) + "."]
    if est.unpriced:
        lines += ["", "NOT PRICED (missing from the price table): " +
                  "; ".join(f"`{a}` ({k})" for a, k in est.unpriced) + ". The total is incomplete."]
    return "\n".join(lines) + "\n"


def evaluate_seeded(base_plan: dict, seeded_dir: Path, policy: dict, as_of: date):
    """Run the checks on every seeded case and compare with the clean plan."""
    manifest = load_json(seeded_dir / "manifest.json")
    clean = {(f.rule, f.address, f.message, f.status) for f in run_policy(base_plan, policy, as_of)}
    rows = []
    for case in manifest["cases"]:
        from .plan import apply_overlay
        variant = apply_overlay(base_plan, load_json(seeded_dir / f"{case['id']}.overlay.json"))
        found = run_policy(variant, policy, as_of)
        new = [f for f in found if (f.rule, f.address, f.message, f.status) not in clean]
        rules = sorted({f.rule for f in new if f.status == "fail"})
        if case["kind"] == "control":
            outcome = "clean (control)" if not new else "false alarm"
        elif any(f.status == "cannot check" for f in new):
            outcome = "cannot check (fails closed)"
        elif case["expected_rules"] and set(case["expected_rules"]) <= set(rules):
            outcome = "detected"
        elif not new:
            outcome = "missed"
        else:
            outcome = "detected by another rule"
        rows.append({"id": case["id"], "change": case["change"], "expected": case["expected_rules"],
                     "rules": rules, "new_findings": len(new), "outcome": outcome,
                     "gate": gate_status(found)})
    c = Counter(r["outcome"] for r in rows)
    kinds = Counter(case["kind"] for case in manifest["cases"])
    summary = {"cases": len(rows), "violations": kinds["violation"], "unknown": kinds["unknown"],
               "controls": kinds["control"], "detected": c["detected"], "missed": c["missed"],
               "cannot check": c["cannot check (fails closed)"], "controls clean": c["clean (control)"],
               "false alarms": c["false alarm"]}
    return rows, summary


def render_seeded(rows, summary) -> str:
    lines = ["# Seeded plans", "", "| Case | Change | Expected | Fired | New findings | Gate | Outcome |",
             "| --- | --- | --- | --- | ---: | ---: | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['change']} | {', '.join(r['expected']) or '-'} | "
                     f"{', '.join(r['rules']) or '-'} | {r['new_findings']} | {r['gate']} | {r['outcome']} |")
    s = summary
    lines += ["", f"Seeded violations: {s['violations']}; detected {s['detected']}, missed {s['missed']}. "
                  f"Unknown until apply: {s['unknown']}, failed closed {s['cannot check']}. "
                  f"Controls clean: {s['controls clean']} of {s['controls']}. False alarms: {s['false alarms']}."]
    return "\n".join(lines) + "\n"


def render_teardown(findings, title: str, inventory: bool) -> str:
    lines = [f"# Teardown check: {title}", ""]
    lines += [f"- {k}: {v}" for k, v in TEARDOWN_RULES.items()] + [""]
    lines += findings_table(findings) if findings else ["No findings."]
    lines += ["", f"Findings: {len(findings)}. Ready to destroy: {'yes' if ready(findings) else 'no'}."]
    if inventory:
        left = sum(f.rule == "TD004" for f in findings)
        lines.append(f"After teardown: {left} inventory finding(s). Nothing left behind: {'yes' if not left else 'no'}.")
    return "\n".join(lines) + "\n"


def render_incident(record: dict, record_path: Path, policy: dict, prices: dict, as_of: date) -> str:
    plan = load_plan(record_path.parent / record["environment"])
    start = datetime.fromisoformat(record["created_utc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(record["found_utc"].replace("Z", "+00:00"))
    hours = (end - start).total_seconds() / 3600
    findings = run_policy(plan, policy, as_of)
    est = estimate(plan, prices)
    rules = sorted({f.rule for f in findings if f.status == "fail"})
    budget = record["counterfactual_budget_usd"]
    marks = ", ".join(f"{p}% after {hours_to_threshold(est.hourly, budget, p):.1f} h" for p in (50, 80, 100))
    lines = ["# The weekend lab environment (composite incident)", "",
             f"Running from {start:%a %d %b %Y %H:%M} to {end:%a %d %b %Y %H:%M} UTC: {hours:g} hours.",
             f"Fixed cost {money(est.hourly)} per hour; {money(est.hourly * hours)} for the weekend, "
             f"at price table {prices['price_table']} (assumptions; usage-based charges not included).",
             f"Largest line: {max(est.lines, key=lambda x: x.hourly).address}, "
             f"{money(max(x.hourly for x in est.lines))} per hour.",
             f"Policy findings: {sum(f.status == 'fail' for f in findings)} failing across {len(rules)} of 12 rules "
             f"({', '.join(rules)}).",
             f"Had a {money(budget)} monthly budget existed, spend would have crossed {marks}. "
             "Budget alerts arrive after billing data, which can lag by hours."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cloudcheck.report", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "cost", "seeded", "teardown", "incident"):
        p = sub.add_parser(name)
        p.add_argument("--policy", default=DEFAULT_POLICY)
        p.add_argument("--prices", default=DEFAULT_PRICES)
        p.add_argument("--as-of", default="2026-11-30")
        if name in ("check", "cost", "seeded"):
            p.add_argument("plan")
        if name in ("check", "cost"):
            p.add_argument("--overlay")
        if name in ("check", "teardown"):
            p.add_argument("--gate", action="store_true")
        if name == "cost":
            p.add_argument("--hours", type=float)
            p.add_argument("--budget", type=float)
            p.add_argument("--details", action="store_true")
        if name == "seeded":
            p.add_argument("--seeded", required=True)
        if name == "teardown":
            p.add_argument("--apply-plan", required=True)
            p.add_argument("--destroy-plan", required=True)
            p.add_argument("--inventory")
            p.add_argument("--env", default=None)
        if name == "incident":
            p.add_argument("record")
    args = ap.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    policy = load_json(args.policy)
    out, status = "", 0
    if args.cmd == "check":
        plan = load_plan(args.plan, args.overlay)
        out, status = render_check(plan, policy, as_of, Path(args.overlay or args.plan).name)
        status = status if args.gate else 0
    elif args.cmd == "cost":
        plan = load_plan(args.plan, args.overlay)
        out = render_cost(plan, load_json(args.prices), Path(args.overlay or args.plan).name, args.hours,
                          args.budget, args.details)
    elif args.cmd == "seeded":
        rows, summary = evaluate_seeded(load_plan(args.plan), Path(args.seeded), policy, as_of)
        out = render_seeded(rows, summary)
    elif args.cmd == "teardown":
        apply_plan, destroy = load_plan(args.apply_plan), load_plan(args.destroy_plan)
        env = args.env or variable(apply_plan, "env")
        inv = load_json(args.inventory) if args.inventory else None
        findings = check_teardown(apply_plan, destroy, env, inventory=inv, as_of=as_of)
        out = render_teardown(findings, Path(args.destroy_plan).name, inv is not None)
        status = (0 if not findings else 1) if args.gate else 0
    elif args.cmd == "incident":
        out = render_incident(load_json(args.record), Path(args.record), policy, load_json(args.prices), as_of)
    sys.stdout.write(out)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
