"""Command-line reports for Lab 20.1 (provided). Run from starter/ or solution/:

    python -m adoption.report maturity --register 2027-01|2027-06 [--explain TEAM]
    python -m adoption.report tom [--draft]
    python -m adoption.report catalog [--draft]
    python -m adoption.report roi [--draft]
    python -m adoption.report adoption        # shadow AI, amnesty and paste-filter counts
    python -m adoption.report plan            # the rollout's waves, stop rules and engineer-months

Every number Chapter 20 quotes from this lab is printed by one of these commands. All data is synthetic.
"""

from __future__ import annotations

import argparse
import sys

from . import DATA, load_json, load_text
from .catalog import check_aup, check_catalog
from .maturity import assess, criterion_met
from .roi import break_even, check_inputs, evaluate, tornado, values
from .tom import check_tom

CATALOG_AS_OF = "2027-06-15"


def _usd(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def render_maturity(register_name: str, explain: str | None = None) -> str:
    model = load_json(DATA / "maturity" / "model.json")
    reg = load_json(DATA / "maturity" / f"evidence-{register_name}.json")
    result = assess(model, reg)
    dims = list(model["dimensions"])
    lines = [f"# Maturity from evidence, as of {reg['as_of']} (self-rating in brackets)", "",
             "| Team | " + " | ".join(dims) + " |", "| --- |" + " ---: |" * len(dims)]
    over = total = 0
    for team in reg["teams"]:
        cells = []
        for d in dims:
            lvl = result[team][d][0]
            own = reg["self_ratings"][team][d]
            total += 1
            over += own > lvl
            cells.append(f"{lvl} ({own})")
        lines.append(f"| {team} | " + " | ".join(cells) + " |")
    inadmissible = sum(1 for i in reg["evidence"]
                       if not criterion_met(next(c for cs in model["dimensions"].values() for c in cs
                                                 if c["id"] == i["criterion"]), [i],
                                            i["team"] if i["team"] != "*" else reg["teams"][0], reg["as_of"])[0])
    lines += ["", f"Cells where the self-rating is higher than the evidence: {over} of {total}",
              f"Evidence items: {len(reg['evidence'])}; not admissible on their own: {inadmissible}",
              "Lowest dimension per team: " + "; ".join(
                  f"{t} {min(dims, key=lambda d: (result[t][d][0], dims.index(d)))}" for t in reg["teams"])]
    if explain:
        lines += ["", f"## Why {explain} is where it is", "", "| Dimension | Level | First unmet | Reason |",
                  "| --- | ---: | --- | --- |"]
        for d in dims:
            lvl, cid, why = result[explain][d]
            lines.append(f"| {d} | {lvl} | {cid or '-'} | {why} |")
    return "\n".join(lines)


def render_tom(draft: bool) -> str:
    tom = load_json(DATA / "operating-model" / ("tom-draft.json" if draft else "tom-reviewed.json"))
    findings = check_tom(tom)
    fte = sum(c["fte"] for c in tom["capabilities"])
    lines = [f"# Target operating model {tom['version']}", "",
             "| Capability | Accountable | Approvers | Security veto | FTE |", "| --- | --- | --- | --- | ---: |"]
    for c in tom["capabilities"]:
        lines.append(f"| {c['id']} {c['name']} | {c['accountable'] or '-'} | {', '.join(c['approvers'])} | "
                     f"{', '.join(c['security_veto']) or '-'} | {c['fte']:.2f} |")
    lines += ["", f"Capabilities: {len(tom['capabilities'])}; funded effort: {fte:.2f} FTE; findings: {len(findings)}"]
    lines += [f"- {f.rule} {f.subject}: {f.message}" for f in findings]
    return "\n".join(lines)


def _catalog_findings(cat: dict, aup: str, as_of: str) -> list:
    relay = DATA / "catalog" / "relay-4.30.0"
    tom = load_json(DATA / "operating-model" / "tom-reviewed.json")
    cases = load_json(DATA / "catalog" / "safety-cases.json")["cases"]
    findings = check_catalog(cat, load_json(relay / "mcp.json"), load_json(relay / "ai-components.json"),
                             load_json(relay / "agents.json"), as_of, tom["security_people"], cases)
    return findings + check_aup(aup, load_json(DATA / "catalog" / "aup-sections.json")["sections"], cat["version"])


def render_catalog(draft: bool) -> str:
    cat = load_json(DATA / "catalog" / ("catalog-draft.json" if draft else "catalog-reviewed.json"))
    aup = load_text(DATA / "catalog" / ("aup-draft.md" if draft else "aup-reviewed.md"))
    findings = _catalog_findings(cat, aup, CATALOG_AS_OF)
    february = load_json(DATA / "catalog" / "catalog-2027-02.json")
    feb_findings = _catalog_findings(february, load_text(DATA / "catalog" / "aup-v1.md"), february["approved_on"])
    status: dict[str, int] = {}
    for t in cat["tools"]:
        status[t["status"]] = status.get(t["status"], 0) + 1
    feb_status: dict[str, int] = {}
    for t in february["tools"]:
        feb_status[t["status"]] = feb_status.get(t["status"], 0) + 1
    lines = [f"# Tool and MCP catalogue {cat['version']} (approved {cat['approved_on']}), checked as of "
             f"{CATALOG_AS_OF}", "",
             f"Previous version {february['version']} (approved {february['approved_on']}, with aup-v1): entries "
             + ", ".join(f"{k} {v}" for k, v in sorted(feb_status.items())) + f"; findings: {len(feb_findings)}", "",
             "| Tool | Kind | Status | Highest data class | Owner |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {t['id']} | {t['kind']} | {t['status']} | {t['max_data_class']} | {t['owner'] or '-'} |"
              for t in cat["tools"]]
    lines += ["", "Entries: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())) +
              f"; findings: {len(findings)}"]
    if findings:
        rules = sorted({f.rule for f in findings})
        lines.append(f"Rules with findings: {len(rules)} ({', '.join(rules)})")
        lines += [f"- {f.rule} {f.subject}: {f.message}" for f in findings]
    return "\n".join(lines)


def render_roi(draft: bool) -> str:
    data = load_json(DATA / "roi" / ("inputs-draft.json" if draft else "inputs-reviewed.json"))
    inputs = data["inputs"]
    findings = check_inputs(inputs)
    lines = [f"# ROI model {data['version']}", "",
             "| Input | Status | Source | Value | Low | High | Unit |", "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for i in inputs:
        lines.append(f"| {i['id']} | {i['status'] or '-'} | {i['source']['kind']} | {i['value']:g} | {i['low']:g} | "
                     f"{i['high']:g} | {i['unit']} |")
    n_meas = sum(1 for i in inputs if i["status"] == "measured")
    n_proj = sum(1 for i in inputs if i["status"] == "projected")
    lines += ["", f"Inputs: {len(inputs)} ({n_meas} measured, {n_proj} projected); findings: {len(findings)}"]
    if findings:
        rules = sorted({f.rule for f in findings})
        lines.append(f"Rules with findings: {len(rules)} ({', '.join(rules)})")
        lines += [f"- {f.rule} {f.subject}: {f.message}" for f in findings]
        lines += ["", "Refused: the model does not run on inputs with findings."]
        return "\n".join(lines)
    v = values(inputs)
    pilot_gross = 190 * (v["author_hours_saved"] - v["review_hours_added"])
    lines += ["", "## Measured only (the pilot, no projection)", "",
              f"Net hours per agent change: {v['author_hours_saved'] - v['review_hours_added']:.2f} "
              f"(author {v['author_hours_saved']:.2f} saved, review {v['review_hours_added']:.2f} added); "
              f"over the pilot's 190 agent changes: {pilot_gross:.0f} hours, before any realization share"]
    r = evaluate(v)
    lines += ["", "## Projected: the twelve-month rollout (base values)", "",
              f"Agent changes: {r['agent_changes']:,.0f}; gross hours released: {r['gross_hours']:,.0f}; "
              f"failure hours: {r['failure_hours']:,.0f}; value per hour: ${r['per_hour']:.2f}",
              f"Benefit: {_usd(r['benefit'])}",
              "Cost: " + _usd(r["cost"]) + " (" + ", ".join(
                  f"{k[5:].replace('_', ' ')} {_usd(r[k])}" for k in r if k.startswith("cost_")) + ")",
              f"Net: {_usd(r['net'])}"]
    steady = evaluate(dict(v, engineer_months_adopted=v["engineers"]), months=1, include_training=False)
    steady_inputs = [dict(i, value=v["engineers"]) if i["id"] == "engineer_months_adopted" else i for i in inputs]
    steady_be = break_even(steady_inputs, "author_hours_saved", months=1, include_training=False)
    lines += ["", f"Steady month after wave 3 (34 engineers, no training): benefit {_usd(steady['benefit'])}, "
                  f"cost {_usd(steady['cost'])}, net {_usd(steady['net'])}",
              f"Break-even author hours saved per agent change (others at base): "
              f"{break_even(inputs, 'author_hours_saved'):.2f}",
              f"Break-even realization share (others at base): {break_even(inputs, 'realization'):.2f}",
              f"Break-even author hours saved in the steady month: {steady_be:.2f} "
              f"(net of review: {steady_be - v['review_hours_added']:.2f})"]
    lines += ["", "## Tornado: net at each input's low and high, others at base", "",
              "| Input | Status | Net at low | Net at high | Swing |", "| --- | --- | ---: | ---: | ---: |"]
    status = {i["id"]: i["status"] for i in inputs}
    for iid, nlo, nhi, swing in tornado(inputs):
        lines.append(f"| {iid} | {status[iid]} | {_usd(nlo)} | {_usd(nhi)} | {_usd(swing)} |")
    return "\n".join(lines)


def render_adoption() -> str:
    d = load_json(DATA / "adoption" / "shadow-ai.json")
    lines = ["# Shadow AI and reporting (four teams, anonymous, aggregate only)", ""]
    for s in d["surveys"]:
        lines.append(f"- {s['date']}: {s['used_personal_ai_for_work_last_month']} of {s['respondents']} respondents "
                     f"({s['respondents']} of {s['of']} engineers answered) used a personal AI account for work in "
                     f"the last month")
    a, p = d["amnesty"], d["paste_filter_blocks"]
    t = d["first_test"]
    lines += [f"- Amnesty {a['from']} to {a['to']}: {a['reports']} reports; credentials rotated: "
              f"{a['credentials_rotated']} ({a['credential']})",
              f"- The policy's first test: {t['what']}; reported in the amnesty: "
              f"{'yes' if t['reported_in_amnesty'] else 'no'}; found by {t['found_by']}; key rotated {t['key_rotated']}",
              f"- Paste filter, {p['from']} to {p['to']}: {p['blocked']} pastes containing a secret blocked"]
    return "\n".join(lines)


def render_plan() -> str:
    p = load_json(DATA / "roi" / "plan.json")
    lines = [f"# Rollout plan {p['version']}, approved {p['approved_on']}", "",
             "| Wave | Teams | Engineers | Start | Months in horizon | Engineer-months | Gate |",
             "| ---: | --- | ---: | --- | ---: | ---: | --- |"]
    total = 0
    for w in p["waves"]:
        em = w["engineers"] * w["months"]
        total += em
        lines.append(f"| {w['wave']} | {', '.join(w['teams'])} | {w['engineers']} | {w['start']} | {w['months']} | "
                     f"{em} | {w['gate']} |")
    lines += ["", f"Engineer-months with agents to {p['horizon'][1]}: {total}", f"Wave order drawn by lot on "
              f"{p['order_drawn_by_lot']}", f"Holdout: {p['holdout']}", f"Comparisons: {p['comparisons']}", "",
              "Stop rules:"]
    lines += [f"- {s}" for s in p["stop_rules"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m adoption.report")
    ap.add_argument("command", choices=["maturity", "tom", "catalog", "roi", "adoption", "plan"])
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--register", default="2027-01", choices=["2027-01", "2027-06"])
    ap.add_argument("--explain")
    a = ap.parse_args(argv)
    if a.command == "maturity":
        text = render_maturity(a.register, a.explain)
    elif a.command in ("tom", "catalog", "roi"):
        text = {"tom": render_tom, "catalog": render_catalog, "roi": render_roi}[a.command](a.draft)
    else:
        text = {"adoption": render_adoption, "plan": render_plan}[a.command]()
    sys.stdout.write(text + "\n")
    return 1 if a.command in ("tom", "catalog", "roi") and "findings: 0" not in text else 0


if __name__ == "__main__":
    sys.exit(main())
