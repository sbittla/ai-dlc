"""Lab 10.1's reports: every number Chapter 10 quotes from the lab is printed here (provided).

    python -m agentlab.report incident
    python -m agentlab.report compare --split heldout      (or dev)
    python -m agentlab.report paired --split heldout
    python -m agentlab.report slices --split heldout
    python -m agentlab.report trajectory --split heldout
    python -m agentlab.report budgets
    python -m agentlab.report live --task HT-031             (optional; RELAY_LAB_LIVE=1, never in tests)

Run from starter/ or solution/. All results are simulated (data/simulator.json).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from . import DATA_DIR
from .calibrate import proposed_budgets
from .compare import compare, gate
from .evaluate import DESIGNS, LABELS, by_design, config, evaluate, majority, routed_without_review, summarize
from .incident import replay
from .stats import paired_sample_size, wilson_interval

SIM = "Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12."


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def usd(x: float) -> str:
    return f"${x:,.2f}" if x >= 1 else f"${x:.3f}"


def points(x: float) -> str:
    return f"{x:+.1f}"


def report_incident() -> str:
    rows = [("none", "As run: no budget, transcript hand-offs, approval as the only stop"),
            ("full", "With 4.24.0's controls: dev-calibrated budget, repeated-failure stop, summary hand-offs"),
            ("repeat_only", "Repeated-failure stop and summary hand-offs, no budget")]
    lines = ["# The opening incident, replayed", "", SIM, "",
             "| Configuration | Stopped by | Rounds | Model calls | Input tokens | Output tokens | Cost | Minutes |"
             " Largest prompt (tokens) |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode, label in rows:
        r = replay(mode)
        lines.append(f"| {label} | {r.reason} | {r.rounds} | {r.calls} | {r.input_tokens:,} | {r.output_tokens:,} | "
                     f"{usd(r.usd)} | {r.seconds / 60:.1f} | {r.largest_input:,} |")
    r = replay("none")
    lines += ["", "As run, by agent:", "", "| Agent | Model calls | Cost |", "| --- | ---: | ---: |"]
    for agent in ("planner", "supervisor", "coder", "tester", "reviewer"):
        lines.append(f"| {agent} | {r.by_agent_calls.get(agent, 0)} | {usd(r.by_agent_usd.get(agent, 0.0))} |")
    growth = sum(s["output"] + s.get("result", 0) for s in load_pipeline()["round"])
    lines += ["", f"Commits pushed by the coder: {r.commits}. Review comments posted: {r.review_comments}.",
              f"The shared transcript grew by {growth:,} tokens a round; at the start of round 3 it was "
              f"{r.round_start_tokens[2]:,} tokens.",
              f"Round 1 cost {usd(r.round_usd[0])}; round 80 cost {usd(r.round_usd[79])}; the last complete round, "
              f"{len(r.round_usd)}, cost {usd(r.round_usd[-1])}.",
              f"Mean input per call: {r.input_tokens // r.calls:,} tokens; the window ({1000000:,}) was full "
              f"from round {first_full_round()}."]
    rate = json.loads((DATA_DIR / "simulator.json").read_text(encoding="utf-8"))["latency"]["input_tokens_per_s"]
    half = replay("none", input_tokens_per_s=rate / 2)
    lines += [f"Assumed prompt processing: {rate:,} input tokens per second, chosen with the token sizes so the loop "
              f"fills the six-hour limit. At half that rate the same loop completes {half.rounds - 1} rounds "
              f"({half.calls} calls) and costs {usd(half.usd)} before the limit."]
    return "\n".join(lines)


def load_pipeline() -> dict:
    return json.loads((DATA_DIR / "incident" / "pipeline.json").read_text(encoding="utf-8"))


def first_full_round() -> int:
    cfg = load_pipeline()
    base = cfg["system_tokens"] + cfg["task_tokens"]
    shared = cfg["planner"]["output"] + cfg["planner"]["read_tokens"]
    for rnd in range(1, 10_000):
        for step in cfg["round"]:
            if base + shared >= cfg["window_tokens"]:
                return rnd
            shared += step["output"] + step.get("result", 0)
    raise AssertionError("never full")


def report_compare(split: str) -> str:
    records = evaluate(split)
    lines = [f"# Four designs on the {split} split", "", SIM, "",
             "| Design | Tasks right (majority of 3 runs) | Wilson 95% | Runs right | Cost per run | Cost per success |"
             " Median s | p90 s | Model calls per run | Tool calls per run | Wrong PRs (runs) | Budget stops |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in DESIGNS:
        s = summarize(by_design(records, d))
        lines.append(f"| {LABELS[d]} | {s['tasks_succeeded']} of {s['tasks']} ({pct(s['rate'])}) | "
                     f"{pct(s['low'])} to {pct(s['high'])} | {pct(s['run_rate'])} | {usd(s['usd_per_run'])} | "
                     f"{usd(s['usd_per_success'])} | {s['median_s']:.0f} | {s['p90_s']:.0f} | {s['model_calls']:.1f} | "
                     f"{s['tool_calls']:.1f} | {s['wrong_prs']} of {s['runs']} | {s['budget_stops']} |")
    if split == "dev":
        s = summarize(list(routed_without_review("dev")))
        lines.append(f"| Routed without its review step (dev only) | {s['tasks_succeeded']} of {s['tasks']} "
                     f"({pct(s['rate'])}) | {pct(s['low'])} to {pct(s['high'])} | {pct(s['run_rate'])} | "
                     f"{usd(s['usd_per_run'])} | {usd(s['usd_per_success'])} | {s['median_s']:.0f} | {s['p90_s']:.0f} | "
                     f"{s['model_calls']:.1f} | {s['tool_calls']:.1f} | {s['wrong_prs']} of {s['runs']} | "
                     f"{s['budget_stops']} |")
    routed = by_design(records, "routed")
    esc = [r for r in routed if r.escalated]
    lines += ["", f"Routed runs that escalated to the agent: {len(esc)} of {len(routed)} ({pct(len(esc) / len(routed))}); "
              f"of those, {sum(r.success for r in esc)} succeeded and {sum(r.status == 'stopped' for r in esc)} "
              f"stopped at the budget."]
    return "\n".join(lines)


def report_paired(split: str) -> str:
    cfg, designs, _ = config()
    records = evaluate(split)
    ref = designs["reference"]
    lines = [f"# Paired comparisons with the {LABELS[ref].lower()} ({split} split)", "", SIM,
             "Differences are candidate minus reference, in points, of the share of runs with the outcome; intervals"
             " resample families (cluster bootstrap); b and c count tasks by majority outcome (for wrong PRs, b counts"
             " tasks where only the reference opened a wrong PR by majority); p is exact McNemar.", "",
             "| Candidate | Success difference | 95% interval | b | c | p | Cost per run | Gate | Wrong-PR difference |"
             " 95% interval | b | c | p |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: |"]
    for d in DESIGNS:
        if d == ref:
            continue
        s = compare(records, d, ref, "success")
        w = compare(records, d, ref, "wrong_pr")
        lines.append(f"| {LABELS[d]} | {points(s.diff)} | {points(s.low)} to {points(s.high)} | {s.b} | {s.c} | "
                     f"{s.p:.3f} | {points(100 * s.cost_change)}% | {gate(s, designs['gate'])} | {points(w.diff)} | "
                     f"{points(w.low)} to {points(w.high)} | {w.b} | {w.c} | {w.p:.3f} |")
    maj_r = majority(by_design(records, "routed"))
    maj_s = majority(by_design(records, ref))
    disc = sum(maj_r[t] != maj_s[t] for t in maj_s) / len(maj_s)
    lines += ["", f"Routed and {LABELS[ref].lower()} disagree (by majority) on {pct(disc)} of tasks. At that rate, "
              f"detecting a 5-point difference with 80% power needs {needed(disc, 0.05)} tasks, and a 3-point "
              f"difference {needed(disc, 0.03)}."]
    return "\n".join(lines)


def needed(disc: float, delta: float) -> str:
    try:
        return f"{paired_sample_size(disc, delta):,}"
    except ValueError:
        return "no sample size (the difference exceeds the disagreement)"


def report_slices(split: str) -> str:
    records = evaluate(split)
    shapes = ("local", "cross_file", "out_of_scope")
    lines = [f"# Success by task shape ({split} split, tasks right by majority)", "", SIM, "",
             "| Design | " + " | ".join(shapes) + " |", "| --- |" + " ---: |" * len(shapes)]
    for d in DESIGNS:
        cells = []
        for shape in shapes:
            maj = majority([r for r in by_design(records, d) if r.shape == shape])
            k, n = sum(maj.values()), len(maj)
            lo, hi = wilson_interval(k, n)
            cells.append(f"{k} of {n} ({pct(lo)} to {pct(hi)})")
        lines.append(f"| {LABELS[d]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def report_trajectory(split: str) -> str:
    records = evaluate(split)
    lines = [f"# Trajectories and policy compliance ({split} split)", "", SIM, "",
             "| Design | Steps per run | Refused calls | invalid_args | path_not_allowed | Repeated reads (same file, same run) |"
             " Approvals | Trails verified | Every PR approved first |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for d in DESIGNS:
        rs = by_design(records, d)
        ref = Counter()
        for r in rs:
            ref.update(r.refusals)
        lines.append(f"| {LABELS[d]} | {sum(r.steps for r in rs) / len(rs):.1f} | {sum(ref.values())} | "
                     f"{ref['invalid_args']} | {ref['path_not_allowed']} | {sum(r.redundant_reads for r in rs)} | "
                     f"{sum(r.approvals for r in rs)} | {sum(r.trail_ok for r in rs)} of {len(rs)} | "
                     f"{sum(r.policy_ok for r in rs)} of {len(rs)} |")
    lines += ["", "How runs ended:", "", "| Design | Ending | Runs |", "| --- | --- | ---: |"]
    for d in DESIGNS:
        endings = Counter(ending(r) for r in by_design(records, d))
        for name, n in sorted(endings.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {LABELS[d]} | {name} | {n} |")
    return "\n".join(lines)


def ending(r) -> str:
    if r.status == "finished":
        return "pull request opened (correct)" if r.variant == "correct" else "pull request opened (wrong)"
    if r.reason.startswith("repeated_failure"):
        return "handed back: repeated failure"
    if r.status == "handed_back":
        return "handed back: " + r.reason.replace("agent:", "")
    return r.reason


def report_budgets() -> str:
    _, designs, _ = config()
    lines = ["# Budgets set from the dev split", "", SIM,
             "1.5 times the 95th percentile of successful dev runs under the calibration budget, rounded up.", "",
             "| Design | Successful dev runs | p95 steps | p95 cost | p95 seconds | Budget: steps | Budget: cost |"
             " Budget: seconds | In designs.json |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for d, v in proposed_budgets().items():
        p, b = v["p95"], v["budget"]
        same = designs["designs"][d]["budget"] == b
        lines.append(f"| {LABELS[d]} | {p['successful_runs']} | {p['steps']} | {usd(p['usd'])} | {p['seconds']:.0f} | "
                     f"{b['max_steps']} | ${b['max_usd']:.2f} | {b['max_seconds']} | {'yes' if same else 'NO'} |")
    return "\n".join(lines)


REPORTS = {"incident": lambda a: report_incident(), "compare": lambda a: report_compare(a.split),
           "paired": lambda a: report_paired(a.split), "slices": lambda a: report_slices(a.split),
           "trajectory": lambda a: report_trajectory(a.split), "budgets": lambda a: report_budgets()}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m agentlab.report")
    parser.add_argument("report", choices=sorted(REPORTS) + ["live"])
    parser.add_argument("--split", default="heldout", choices=["dev", "heldout"])
    parser.add_argument("--task", default="HT-031")
    args = parser.parse_args()
    if args.report == "live":
        from .live import run_live
        print(run_live(args.task))
        return
    print(REPORTS[args.report](args))


if __name__ == "__main__":
    main()
