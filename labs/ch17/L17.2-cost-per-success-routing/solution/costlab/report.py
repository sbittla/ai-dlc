"""Lab 17.2's reports (provided). Run from starter/ or solution/:

    python -m costlab.report gate       # what Chapter 7's gate saw: first calls, no clock (TODOs 1, 2)
    python -m costlab.report configs    # the three configurations under Relay's worker rules (TODOs 1, 2)
    python -m costlab.report incident   # the opening incident, day by day, with a spend monitor (TODOs 1, 2)
    python -m costlab.report caching    # prompt caching against the week's arrivals (TODO 3)
    python -m costlab.report abuse      # an hour of stolen tokens against the spend quota (TODO 4)
    python -m costlab.report agents     # Chapter 10's designs: cost per success, cache surcharge, budgets (TODO 5)
"""

from __future__ import annotations

import argparse
import math
import sys

from relay.routing import PRICES_AS_OF, Route, route_problems

from .abuse import ABUSE, burst, ceiling_usd
from .agentcost import design_costs
from .caching import MIN_PREFIX, TTL_S, prefix_cost, simulate, split_streams, week_arrivals
from .compare import CONFIGS, offline, paired, router, run_config, summarize, table
from .incident import INCIDENT, replay, tickets_by_weekday
from .production import MODELS, system_prompt

ATTEMPTS = CONFIGS["worker"]["max_attempts"]
LABELS = {"large": "A: sim-large", "reasoner": "B: sim-reasoner", "routed": "C: routed"}


def money(x: float, digits: int = 6) -> str:
    return f"${x:,.{digits}f}"


def render_gate() -> str:
    lines = ["# What Chapter 7's gate measured: the first call for each ticket and run, with no clock", "",
             "Held-out split of relay-triage-eval 2026.11.1: 200 tickets, 3 runs each. Simulated models.", "",
             "| Configuration | First call correct | Difference (points) | 95% paired interval | Worse / better | "
             "McNemar p | Cost per correct |", "| --- | ---: | ---: | --- | ---: | ---: | ---: |"]
    base = offline("large")
    lines.append(f"| {LABELS['large']} | {base.accuracy:.1%} | n/a | n/a | n/a | n/a | {money(base.usd_per_correct)} |")
    for c in ("reasoner", "routed"):
        o = offline(c)
        p = o.paired
        lines.append(f"| {LABELS[c]} | {o.accuracy:.1%} | {p.diff_points:+.1f} | {p.low:+.1f} to {p.high:+.1f} | "
                     f"{p.worse} / {p.better} | {p.p_value:.3f} | {money(o.usd_per_correct)} |")
    b = offline("reasoner")
    lines += ["", f"Wrong first calls: {1 - base.accuracy:.1%} for A, {1 - b.accuracy:.1%} for B.",
              f"Cost per correct, B against A: {b.usd_per_correct / base.usd_per_correct:.2f} times "
              f"(the gate warns above 1.25 times; the reviewer accepted the warning)."]
    return "\n".join(lines)


def render_configs() -> str:
    r, threshold = router()
    rows = table()
    a = rows[0]
    lines = ["# Three configurations under Relay's worker rules (simulated models and latency)", "",
             f"Prompt {CONFIGS['prompt']}; prices as of {PRICES_AS_OF} (assumptions). Router: Chapter 7's, "
             f"trained on dev, threshold {threshold:g} (the highest catching "
             f"{CONFIGS['configs']['routed']['router_min_recall']:.0%} of hard dev tickets out of fold).", "",
             "| Configuration | Correct | Wrong | To a person | Timeouts | Calls per ticket | Cost per call | "
             "Cost per correct | Call p95 (s) | TTFT p95 (s) | Suggestion p50 (s) | Suggestion p95 (s) |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in rows:
        lines.append(f"| {LABELS[s.config]} | {s.correct} ({s.quality:.1%}) | {s.wrong} | {s.needs_human} | "
                     f"{s.timeouts} | {s.calls_per_run:.3f} | {money(s.usd_per_call)} | {money(s.usd_per_correct)} | "
                     f"{s.call_p95_s:.1f} | {s.ttft_p95_s:.1f} | {s.suggestion_p50_s:.1f} | {s.suggestion_p95_s:.1f} |")
    lines += ["", f"Runs per configuration: {a.runs}. C sends {rows[2].hard_route_share:.1%} of runs to sim-reasoner.", "",
              "| Against A | Difference (points) | 95% paired interval | Worse / better | McNemar p | Cost per correct |",
              "| --- | ---: | --- | ---: | ---: | ---: |"]
    for s in rows[1:]:
        p = paired(s.config)
        lines.append(f"| {LABELS[s.config]} | {p.diff_points:+.1f} | {p.low:+.1f} to {p.high:+.1f} | {p.worse} / "
                     f"{p.better} | {p.p_value:.3f} | {s.usd_per_correct / a.usd_per_correct:.2f} times |")
    over = {r.config: (sum(o.seconds > 60 for o in run_config(r.config)),
                       sum(o.seconds == 60 for o in run_config(r.config))) for r in rows}
    lines += ["", "Triages taking more than 60 s / exactly 60 s: " + ", ".join(
        f"{LABELS[c]} {a} / {b}" for c, (a, b) in over.items()) + ".",
              "Wrong share of suggestions: " + ", ".join(
        f"{LABELS[s.config]} {s.wrong_share_of_suggestions:.1%}" for s in rows) + "."]
    m = MODELS["models"]["sim-reasoner"]
    ttft_p99 = round(m["ttft_median_s"] * math.exp(2.326 * m["ttft_sigma"]), 1)
    for name, route in (("B's route", CONFIGS["configs"]["reasoner"]["default"]),
                        ("C's hard route", CONFIGS["configs"]["routed"]["hard"])):
        problems = route_problems(Route(name, route["model"], CONFIGS["prompt"], route["max_output_tokens"],
                                        route["timeout_s"]), ttft_p99_s=ttft_p99, output_tokens_per_s=m["output_tokens_per_s"])
        lines.append(f"Route check, {name} (p99 time to first token before reasoning {ttft_p99:g} s): "
                     f"{problems[0] if problems else 'no problem'}.")
    return "\n".join(lines)


def render_incident() -> str:
    r = replay()
    lines = ["# The opening incident, replayed (composite; expected values per day)", "",
             f"Gate run {INCIDENT['gate_run']}; switched on the 15:00 UTC train of {INCIDENT['switched']}; "
             f"noticed {INCIDENT['noticed']}; reverted {INCIDENT['reverted']}.",
             f"Tickets per day, Monday to Sunday: {', '.join(f'{n:,}' for n in tickets_by_weekday())}.",
             f"Full days on the new model: {r.days} ({r.first_day} to {r.last_day}), {r.tickets:,} tickets.",
             f"Triage cost over those days: {money(r.cost_new, 2)} on sim-reasoner, against {money(r.cost_old, 2)} "
             f"on sim-large ({r.cost_new / r.cost_old:.2f} times; {money(r.cost_new - r.cost_old, 2)} more).",
             f"Tickets handed to a person instead of getting a suggestion: about {r.to_a_person:,.0f}.",
             f"Cost per call, new against old: {r.call_ratio:.2f} times.",
             f"A spend monitor on cost per suggestion delivered (no labels needed; baseline A "
             f"{money(r.suggestion_baseline)}, tolerance 25%, three-day window) would first have alerted on "
             f"{r.suggestion_alert}, at {money(r.suggestion_value)} per suggestion.",
             f"With a daily count of correct triages, which production does not have, the same monitor on cost per "
             f"correct triage would also have alerted on {r.first_alert}, at {money(r.alert_value)}."]
    return "\n".join(lines)


def render_caching() -> str:
    t = week_arrivals()
    system_tokens = len(system_prompt()) // 4
    lines = ["# Prompt caching against the week of 1 February 2027 (assumed provider rules)", "",
             f"Rules: minimum cacheable prefix {MIN_PREFIX} tokens; entry lives {TTL_S:g} s from the start of the last "
             "call that wrote or read it; writes 1.25 times the input price, reads 5% (sim-large prices).",
             f"Calls: one per ticket, {len(t):,} in the week.", "",
             "| Cached prefix (tokens) | Writes | Reads | Uncached | Hit rate | Prefix cost without caching | With caching |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for p in (system_tokens, 1200, 4000):
        r = simulate(t, p)
        without, with_cache = prefix_cost(r, p)
        lines.append(f"| {p:,} | {r.writes:,} | {r.reads:,} | {r.uncached:,} | {r.hit_rate:.1%} | {money(without, 2)} | "
                     f"{money(with_cache, 2)} |")
    share = summarize("routed", run_config("routed")).hard_route_share
    easy, hard = split_streams(t, share)
    lines += ["", f"triage-v3.1's system prompt is about {system_tokens} tokens (four characters a token), under the "
              f"{MIN_PREFIX}-token minimum, so caching it saves nothing.",
              f"Split across two models as configuration C splits it ({share:.1%} to sim-reasoner), a 1,200-token "
              f"prefix hits {simulate(easy, 1200).hit_rate:.1%} of the time on sim-large and "
              f"{simulate(hard, 1200).hit_rate:.1%} on sim-reasoner: each model keeps its own cache."]
    weekly = summarize("routed", run_config("routed"))
    lines.append(f"Batch pricing: re-running this lab's held-out evaluation of C ({weekly.runs} triages) costs "
                 f"{money(weekly.usd_per_run * weekly.runs, 2)}; at an assumed 50% batch discount, "
                 f"{money(weekly.usd_per_run * weekly.runs / 2, 2)}. Triage itself cannot wait for a batch.")
    return "\n".join(lines)


def render_abuse() -> str:
    run_cost = summarize("routed", run_config("routed")).usd_per_run
    lines = ["# One hour of stolen tokens against the triage spend quota (simulated traffic, real SpendQuota)", "",
             f"{ABUSE['start_utc']}, {ABUSE['minutes']} minutes. Each queued ticket reserves {money(ceiling_usd())} "
             f"(C's hard-route ceiling). Limits per UTC day: user ${ABUSE['limits']['user']:.2f}, workspace "
             f"${ABUSE['limits']['workspace']:.2f}. Expected spend uses C's mean cost per ticket, {money(run_cost)}; "
             f"ceiling spend assumes every ticket takes the hard route for all {ATTEMPTS} attempts, "
             f"{money(ceiling_usd() * ATTEMPTS)} a ticket.",
             f"A user's ${ABUSE['limits']['user']:.2f} buys {int(ABUSE['limits']['user'] // ceiling_usd())} tickets at "
             f"one call's ceiling; at C's mean cost it would pay for {ABUSE['limits']['user'] / run_cost:,.0f}.", "",
             "| Scenario | Quotas | Attacker sent | Attacker accepted | Real users sent | Real users accepted | "
             "First refusal (s) | Reserved | Expected spend | Ceiling spend | Refusals recorded |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in ABUSE["scenarios"]:
        for q in (False, True):
            b = burst(s, q)
            n = b.attacker_accepted + b.legit_accepted
            spend, ceiling = n * run_cost, n * ceiling_usd() * ATTEMPTS
            lines.append(f"| {s} | {'yes' if q else 'no'} | {b.attacker_sent:,} | {b.attacker_accepted:,} | "
                         f"{b.legit_sent} | {b.legit_accepted} | {'n/a' if b.first_refusal_s is None else b.first_refusal_s} | "
                         f"{money(b.reserved_usd, 2)} | {money(spend, 2)} | {money(ceiling, 2)} | "
                         f"{b.refusals_recorded:,} |")
    return "\n".join(lines)


def render_agents() -> str:
    lines = ["# Chapter 10's designs: cost per success, the cache-write surcharge and recalibrated budgets", "",
             "Held-out runs from Lab 10.1 (simulated sim-large; prices as of 2027-01-12). Surcharge: every uncached "
             "input token of a caching run written at 1.25 times the input price (assumption).", "",
             "| Design | Runs | Successes | Cost per run | Cost per success | With surcharge | With no caching | "
             "Budget (Ch10) | Recalibrated |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in design_costs():
        lines.append(f"| {d.design} | {d.runs} | {d.successes} | {money(d.per_run, 3)} | {money(d.per_success, 3)} | "
                     f"{money(d.per_success_surcharged, 3)} | {money(d.per_success_uncached, 3)} | "
                     f"{money(d.old_budget, 2)} | {money(d.recalibrated_budget, 2)} |")
    lines += ["", "Recalibrated: 1.5 times the 95th percentile of successful dev runs' cost with the surcharge, "
              "rounded up to $0.05, as Lab 10.1 set its budgets."]
    return "\n".join(lines)


RENDER = {"gate": render_gate, "configs": render_configs, "incident": render_incident, "caching": render_caching,
          "abuse": render_abuse, "agents": render_agents}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m costlab.report")
    ap.add_argument("what", choices=sorted(RENDER))
    args = ap.parse_args(argv)
    sys.stdout.write(RENDER[args.what]() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
