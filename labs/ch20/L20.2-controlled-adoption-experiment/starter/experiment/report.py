"""Command-line reports for Lab 20.2 (provided). Run from starter/ or solution/:

    python -m experiment.report baseline           # the Q4 2026 baseline and its variance components
    python -m experiment.report power              # power of designs D1-D4, sensitivities, weeks needed
    python -m experiment.report prereg [--draft]   # REG001-REG010 on the reviewed (or draft) pre-registration
    python -m experiment.report readout            # the pre-registered readout of the pilot
    python -m experiment.report roi-inputs         # the measured values Lab 20.1's ROI model uses
    python -m experiment.report config             # the effects configured into the generator, and their size

Every number Chapter 20 quotes from this lab is printed by one of these commands. The data is synthetic and its
effects are configured (data/config.json): read the readout as a demonstration of the method, not as evidence
about coding agents.
"""

from __future__ import annotations

import argparse
import hashlib
import statistics
import sys

from . import DATA, load_changes, load_json
from .analysis import (failure_rates, net_hours_saved, pilot_rows, skills_mcnemar, team_medians,
                       within_engineer_hours_saved, within_engineer_log_ratio)
from .power import ASSUMPTIONS, DESIGNS, simulate_power, variance_components, weeks_for_power
from .prereg import check_frozen, check_prereg, registered_test

PILOT = ("integrations", "analytics")
COMPARISON = ("mobile", "marketplace")
MIN_SURVEY_N = 5  # team results from fewer respondents are suppressed, to keep the survey anonymous


def team_sizes() -> dict[str, int]:
    people = load_json(DATA / "people.json")["engineers"]
    sizes: dict[str, int] = {}
    for p in people:
        sizes[p["team"]] = sizes.get(p["team"], 0) + 1
    return sizes


def baseline_rows(rows=None) -> list[dict]:
    return [r for r in (rows or load_changes()) if r["period"] == "baseline"]


def render_baseline() -> str:
    rows = baseline_rows()
    comps = variance_components(rows)
    sizes = team_sizes()
    per_week = len(rows) / (sum(sizes.values()) * 13)
    lines = ["# Baseline quarter (13 weeks, 5 October 2026 to 1 January 2027, four teams)", "",
             f"Changes: {len(rows)}; engineers: {sum(sizes.values())}; changes per engineer-week: {per_week:.2f}",
             f"Mean author hours per change: {statistics.mean(r['author_hours'] for r in rows):.2f}; "
             f"mean review hours per change: {statistics.mean(r['review_hours'] for r in rows):.2f}",
             f"Median change lead time: {statistics.median(r['lead_time_hours'] for r in rows):.1f} h", "",
             "Variance components of log lead time (method of moments; four teams make the team term rough):",
             f"sd_team {comps['sd_team']:.3f}, sd_engineer {comps['sd_engineer']:.3f}, "
             f"sd_residual {comps['sd_residual']:.3f}"]
    return "\n".join(lines)


def render_power() -> str:
    comps = variance_components(baseline_rows())
    sizes = team_sizes()
    lines = ["# Power by design (simulated, 1,000 pilots each, 13 weeks, two-sided alpha 0.05)", "",
             "Assumptions not estimable from the baseline: " +
             ", ".join(f"{k} {v}" for k, v in ASSUMPTIONS.items()), "",
             "| Design | Unit | Engineers | Power at 0.80 | Power at 0.85 | Power at 0.90 |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for d, spec in DESIGNS.items():
        n = sum(sizes[t] for t in spec["teams"])
        p = [simulate_power(d, comps, sizes, r) for r in (0.80, 0.85, 0.90)]
        lines.append(f"| {d} {spec['name']} | {spec['unit']} | {n} | {p[0]:.3f} | {p[1]:.3f} | {p[2]:.3f} |")
    lines += ["", "Sensitivity at a true ratio of 0.80:"]
    for sd in (0.0, 0.05, 0.10):
        lines.append(f"- D1 with sd_team_period {sd:.2f}: power "
                     f"{simulate_power('D1', comps, sizes, 0.80, assumptions={'sd_team_period': sd}):.3f}")
    for c in (0.30, 0.50):
        lines.append(f"- D2 with contamination_engineer {c:.2f}: power "
                     f"{simulate_power('D2', comps, sizes, 0.80, assumptions={'contamination_engineer': c}):.3f}")
    for c in (0.20, 0.40):
        lines.append(f"- D3 with contamination_task {c:.2f}: power "
                     f"{simulate_power('D3', comps, sizes, 0.80, assumptions={'contamination_task': c}):.3f}")
    w = weeks_for_power("D3", comps, sizes, 0.85)
    lines.append(f"- D3 needs {w} weeks for 80% power at a true ratio of 0.85")
    sign = [simulate_power("D3", comps, sizes, r, test="sign") for r in (0.80, 0.85, 0.90)]
    sign4 = [simulate_power("D4", comps, sizes, r, test="sign") for r in (0.80, 0.85, 0.90)]
    lines += ["", "The same task-level designs analyzed with the exact sign test instead of the paired t-test:",
              f"- D3 sign test: power {sign[0]:.3f}, {sign[1]:.3f}, {sign[2]:.3f} at 0.80, 0.85, 0.90",
              f"- D4 sign test: power {sign4[0]:.3f}, {sign4[1]:.3f}, {sign4[2]:.3f} at 0.80, 0.85, 0.90",
              f"- D3 with the sign test needs {weeks_for_power('D3', comps, sizes, 0.80, test='sign')} weeks for 80% "
              f"power at a true ratio of 0.80"]
    return "\n".join(lines)


def render_prereg(draft: bool) -> str:
    reg = load_json(DATA / "prereg" / ("prereg-draft.json" if draft else "prereg-reviewed.json"))
    comps = variance_components(baseline_rows())
    test = registered_test(reg)
    computed = simulate_power(reg["design"], comps, team_sizes(), reg["power"]["mde_ratio"],
                              test=test if reg["design"] in ("D3", "D4") else "t")
    sha = hashlib.sha256((DATA / "assignments.csv").read_bytes()).hexdigest()
    reg_bytes = (DATA / "prereg" / ("prereg-draft.json" if draft else "prereg-reviewed.json")).read_bytes()
    frozen = load_json(DATA / "prereg" / "frozen.json")
    findings = check_prereg(reg, computed, sha) + check_frozen(reg_bytes, frozen, reg["id"], reg["start"])
    lines = [f"# Pre-registration {reg['id']} {reg['version']} ({'draft' if draft else 'reviewed'})", "",
             f"Design {reg['design']}; registered test: {'sign test' if test == 'sign' else 'paired t-test'}; "
             f"stated power {reg['power']['power']:.3f} at ratio {reg['power']['mde_ratio']:.2f}; "
             f"recomputed {computed:.3f}", f"Findings: {len(findings)}"]
    if findings:
        rules = sorted({f.rule for f in findings})
        lines.append(f"Rules with findings: {len(rules)} ({', '.join(rules)})")
        lines += ["", "| Rule | Finding |", "| --- | --- |"] + [f"| {f.rule} | {f.message} |" for f in findings]
    return "\n".join(lines)


def _fmt_ratio(name: str, r: dict) -> str:
    return (f"| {name} | {r['estimate']:.2f} | {r['low']:.2f} to {r['high']:.2f} | {r['t_test_p']:.3f} | "
            f"{r['negative']} lower, {r['positive']} higher | {r['sign_test_p']:.3f} |")


def _fmt_hours(name: str, r: dict) -> str:
    return (f"| {name} | {r['estimate']:.2f} | {r['low']:.2f} to {r['high']:.2f} | {r['t_test_p']:.3f} | "
            f"{r['positive']} saved, {r['negative']} lost | {r['sign_test_p']:.3f} |")


def render_readout() -> str:
    rows = load_changes()
    p = pilot_rows(rows)
    n_a = sum(1 for r in p if r["arm"] == "agent")
    lines = ["# Pilot readout (pre-registered analysis; synthetic, configured data)", "",
             f"Pilot changes in the two pilot teams: {len(p)} ({n_a} agent, {len(p) - n_a} control); "
             f"engineers with both arms: {within_engineer_log_ratio(p, 'lead_time_hours')['engineers']}", "",
             "Ratios of geometric means, agent over control, within engineer (95% paired t interval, 14 df).",
             "Secondary outcomes are unadjusted for multiplicity and descriptive, as registered.", "",
             "| Outcome | Ratio | 95% interval | t-test p | Engineers | Sign test p |",
             "| --- | ---: | --- | ---: | --- | ---: |",
             _fmt_ratio("Change lead time (primary)", within_engineer_log_ratio(p, "lead_time_hours")),
             _fmt_ratio("Author hours", within_engineer_log_ratio(p, "author_hours")),
             _fmt_ratio("Review hours", within_engineer_log_ratio(p, "review_hours")),
             _fmt_ratio("Review wait", within_engineer_log_ratio(p, "review_wait_hours")), "",
             "Hours per change, control minus agent, within engineer (arithmetic means):", "",
             "| Outcome | Hours | 95% interval | t-test p | Engineers | Sign test p |",
             "| --- | ---: | --- | ---: | --- | ---: |",
             _fmt_hours("Author hours saved", within_engineer_hours_saved(p, "author_hours")),
             _fmt_hours("Review hours saved", within_engineer_hours_saved(p, "review_hours")),
             _fmt_hours("Net hours saved", net_hours_saved(p))]
    a = within_engineer_hours_saved(p, "author_hours")
    lines += ["", f"Check: the percentile cluster bootstrap for author hours saved gives {a['boot_low']:.2f} to "
              f"{a['boot_high']:.2f}, against the t interval's {a['low']:.2f} to {a['high']:.2f}; "
              f"{100 * (1 - (a['boot_high'] - a['boot_low']) / (a['high'] - a['low'])):.0f}% narrower with 15 clusters"]
    f = failure_rates(p)
    lines += ["", f"Change fail rate: agent {f['agent_failed']} of {f['agent_n']}, control {f['control_failed']} of "
              f"{f['control_n']}; within-engineer difference {f['difference_points']:+.1f} points "
              f"({f['low']:+.1f} to {f['high']:+.1f}), t-test p = {f['t_test_p']:.3f}"]
    med = team_medians(rows, "review_wait_hours")
    lines += ["", "Median review wait by team (hours; descriptive, four teams):", "",
              "| Team | Group | Q4 2026 | Pilot |", "| --- | --- | ---: | ---: |"]
    for t in PILOT + COMPARISON:
        lines.append(f"| {t} | {'pilot' if t in PILOT else 'comparison'} | {med[('baseline', t)]:.1f} | "
                     f"{med[('pilot', t)]:.1f} |")
    pilot_wait = statistics.median([r["review_wait_hours"] for r in rows if r["period"] == "pilot" and r["team"] in PILOT])
    comp_wait = statistics.median([r["review_wait_hours"] for r in rows if r["period"] == "pilot" and r["team"] in COMPARISON])
    base_p = statistics.median([r["review_wait_hours"] for r in rows if r["period"] == "baseline" and r["team"] in PILOT])
    base_c = statistics.median([r["review_wait_hours"] for r in rows if r["period"] == "baseline"
                                and r["team"] in COMPARISON])
    ratio_pilot, ratio_base = pilot_wait / comp_wait, base_p / base_c
    lines.append(f"Guardrail: pilot-to-comparison median review wait {ratio_pilot:.2f} in the pilot ({pilot_wait:.1f} h "
                 f"against {comp_wait:.1f} h) and {ratio_base:.2f} in the baseline ({base_p:.1f} h against "
                 f"{base_c:.1f} h); pilot over baseline {ratio_pilot / ratio_base:.2f} (threshold 1.5)")
    survey = load_json(DATA / "survey.json")["teams"]
    perceived = [s for s in survey if "perceived_speedup_on_agent_tasks" in s]
    shown = [s for s in perceived if s["n"] >= MIN_SURVEY_N]
    hidden = [s["team"] for s in perceived if s["n"] < MIN_SURVEY_N]
    n = sum(s["n"] for s in shown)
    mean = sum(s["perceived_speedup_on_agent_tasks"] * s["n"] for s in shown) / n
    lines += ["", f"Perceived time saved on agent tasks (week 13; {', '.join(s['team'] for s in shown)}, n = {n}): "
              f"{100 * mean:.0f}%; not reported for {', '.join(hidden) or 'none'} (n < {MIN_SURVEY_N})"]
    skills = load_json(DATA / "skills.json")
    for label, teams in (("pilot", PILOT), ("comparison", COMPARISON)):
        m = skills_mcnemar(skills, teams)
        lines.append(f"Unassisted debugging, {label} teams: passed {m['pass_before']} of {m['engineers']} before, "
                     f"{m['pass_after']} after; discordant {m['b']} and {m['c']}, exact McNemar p = {m['p']:.3f}")
    lines += ["", "Survey means by team (anonymous pulse; descriptive only):", "",
              "| Team | Wave | n | Satisfaction | Review load manageable | Flow | Psychological safety (1-7) |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for s in survey:
        if s["n"] < MIN_SURVEY_N:
            lines.append(f"| {s['team']} | {s['wave']} | {s['n']} | suppressed (n < {MIN_SURVEY_N}) | | | |")
            continue
        lines.append(f"| {s['team']} | {s['wave']} | {s['n']} | {s['satisfaction_1_5']:.2f} | "
                     f"{s['review_load_manageable_1_5']:.2f} | {s['flow_1_5']:.2f} | "
                     f"{s['psychological_safety_1_7']:.2f} |")
    return "\n".join(lines)


def roi_inputs() -> dict:
    """The measured values Lab 20.1's ROI model takes from this lab."""
    rows = load_changes()
    p = pilot_rows(rows)
    base = baseline_rows(rows)
    sizes = team_sizes()
    author = within_engineer_hours_saved(p, "author_hours")
    review = within_engineer_hours_saved(p, "review_hours")
    net = net_hours_saved(p)
    fail = failure_rates(p)
    spend = load_json(DATA / "spend.json")["months"]
    usd = sum(m["model_usd"] for m in spend)
    agent_changes = sum(m["agent_changes"] for m in spend)
    per_week = len(base) / (sum(sizes.values()) * 13)
    return {"net_hours_saved_per_agent_change": (round(net["estimate"], 2), round(net["low"], 2), round(net["high"], 2)),
            "author_hours_saved_per_agent_change": (round(author["estimate"], 2), round(author["low"], 2),
                                                    round(author["high"], 2)),
            "review_hours_added_per_agent_change": (round(-review["estimate"], 2), round(-review["high"], 2),
                                                    round(-review["low"], 2)),
            "change_fail_rate_delta_points": (round(fail["difference_points"], 1), round(fail["low"], 1),
                                              round(fail["high"], 1)),
            "model_usd_per_agent_change": round(usd / agent_changes, 2),
            "changes_per_engineer_month": round(per_week * 52 / 12, 2)}


def render_config() -> str:
    """The effects configured into the generator, and what they imply (provided; read with data/README-data.md)."""
    import importlib.util
    from statistics import NormalDist

    spec = importlib.util.spec_from_file_location("lab202_generator", DATA.parent / "scripts" / "generate_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    cfg = gen.CONFIG
    rng = __import__("random").Random(7)
    eng = {"engineer": "x", "team": "integrations", "level": "senior"}
    logs = []
    for i in range(100_000):
        row = gen.make_change(rng, f"M{i}", eng, 0.0, "pilot", "control", 0, gen.PILOT_START)
        agent = gen.rescale_for_agent(row)
        logs.append(__import__("math").log(float(agent["lead_time_hours"]) / float(row["lead_time_hours"])))
    lead_ratio = __import__("math").exp(sum(logs) / len(logs))
    large = cfg["size_mix"]["L"] * cfg["fail_rate"]["large_extra"]
    pc, pa = cfg["fail_rate"]["control"] + large, cfg["fail_rate"]["agent"] + large
    rows = pilot_rows(load_changes())
    na = sum(1 for r in rows if r["arm"] == "agent")
    nc = len(rows) - na
    z = NormalDist().inv_cdf(0.975)
    se = ((pa * (1 - pa)) / na + (pc * (1 - pc)) / nc) ** 0.5
    power = NormalDist().cdf((pa - pc) / se - z)
    need = (z + NormalDist().inv_cdf(0.80)) ** 2 * (pa * (1 - pa) + pc * (1 - pc)) / (pa - pc) ** 2
    lines = ["# Effects configured into Lab 20.2's generator (not findings)", "",
             f"- Author hours on agent changes: x{cfg['agent_author_factor']['S']} small, "
             f"x{cfg['agent_author_factor']['M']} medium, x{cfg['agent_author_factor']['L']} large",
             f"- Review hours x{cfg['agent_review_factor']}; review wait x{cfg['agent_review_wait_factor']}; "
             f"the pilot teams' shared queue x{cfg['pilot_team_queue_factor']} for both arms",
             f"- Change fail rate: {100 * pc:.1f}% control, {100 * pa:.1f}% agent (a harm of "
             f"{100 * (pa - pc):+.1f} points)",
             f"- Perceived saving asked of the pilot teams: centred on {cfg['perceived_speedup_mean']:.2f}",
             "- Skills and the other survey answers: no difference between groups",
             f"- Expected lead-time ratio under this configuration (100,000 simulated changes): {lead_ratio:.3f}",
             f"- Power of the pilot ({na} agent and {nc} control changes) to detect the configured fail-rate harm, "
             f"two-sided 5%, normal approximation: {power:.2f}",
             f"- Changes per arm needed for 80% power against that harm: {need:,.0f}"]
    return "\n".join(lines)


def render_roi_inputs() -> str:
    lines = ["# Measured inputs for Lab 20.1's ROI model (value, low, high where an interval exists)", ""]
    for k, v in roi_inputs().items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m experiment.report")
    ap.add_argument("command", choices=["baseline", "power", "prereg", "readout", "roi-inputs", "config"])
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args(argv)
    out = {"baseline": render_baseline, "power": render_power, "readout": render_readout,
           "roi-inputs": render_roi_inputs, "config": render_config}.get(a.command)
    text = out() if out else render_prereg(a.draft)
    sys.stdout.write(text + "\n")
    if a.command == "prereg" and "Findings: 0" not in text:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
