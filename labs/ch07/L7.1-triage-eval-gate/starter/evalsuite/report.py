"""Relay's triage eval suite: the gate and the reports Chapter 7 quotes.

Offline (default, free, deterministic; every model is SIMULATED):
    python -m evalsuite.report --data ../data gate --candidate sim-large:triage-v2
    python -m evalsuite.report --data ../data candidates
    python -m evalsuite.report --data ../data incident | leakage | router | stats | agents | dataset

Live (costs money; needs `pip install -e ".[live]"` and credentials):
    python -m evalsuite.report --data ../data gate --live --max-usd 5 \\
        --baseline claude-opus-5-5:triage-v1 --candidate claude-opus-5-5:triage-v2

`gate` exits with status 1 when the candidate fails, so CI can use it directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import agent_eval, dataset, gate, models, prompts, router, runner, stats

BASELINE = "sim-large:triage-v1"
CANDIDATES = ["sim-large:triage-v1.1", "sim-large:triage-v2", "sim-large:triage-v3", "sim-large:triage-v3.1",
              "sim-large-2:triage-v1", "sim-small:triage-v1", "routed:triage-v1"]
ROUTER_RECALL = 0.95
ROW_SEEDS = list(range(1, 31))
NOISE_SEEDS = list(range(101, 141))


class Suite:
    """Everything a report needs: the pinned data, the policy and the candidates."""

    def __init__(self, data: Path, live: bool = False, max_usd: float = 0.0):
        self.data = data
        self.policy = gate.load_policy(data / "gate-policy.json")
        self.tickets = dataset.load_tickets(data / "tickets.jsonl")
        self.gold = {t["id"]: t for t in self.tickets}
        self.dev = dataset.split(self.tickets, "dev")
        self.held = dataset.split(self.tickets, self.policy["split"])
        self.pin = dataset.verify_pin(data, self.policy["dataset"]["name"], self.policy["dataset"]["version"])
        self.repeats = self.policy["repeats"]
        self.live, self.max_usd = live, max_usd
        self._cache: dict[tuple, list[runner.Record]] = {}

    def router(self) -> tuple[router.Router, float]:
        oof = router.out_of_fold_scores(self.dev)
        threshold = router.choose_threshold(oof, [t["difficulty"] == "hard" for t in self.dev], ROUTER_RECALL)
        return router.train(self.dev), threshold

    def client(self, model: str, version: str):
        if self.live:
            inner = models.live_model(model)
            mean_chars = sum(len(t["text"]) for t in self.held) / len(self.held) + 20
            est = models.estimate_call_usd(prompts.PROMPTS[version].full_system(), mean_chars,
                                           inner.price_in_per_mtok, inner.price_out_per_mtok)
            return models.BudgetGuard(inner, self.max_usd / 2, est)  # half the ceiling per candidate
        if model == "routed":
            r, threshold = self.router()
            return router.RoutedModel(models.SimulatedTriageModel("sim-small", version, self.gold),
                                      models.SimulatedTriageModel("sim-large", version, self.gold), r, threshold)
        return models.SimulatedTriageModel(model, version, self.gold)

    def records(self, spec: str, tickets: list[dict] | None = None, repeats: int | None = None) -> list[runner.Record]:
        tickets = self.held if tickets is None else tickets
        repeats = self.repeats if repeats is None else repeats
        key = (spec, tuple(t["id"] for t in tickets), repeats)
        if key not in self._cache:
            model, version = spec.split(":")
            self._cache[key] = runner.run_candidate(spec, self.client(model, version), prompts.PROMPTS[version],
                                                    tickets, repeats)
        return self._cache[key]

    def leakage(self, version: str) -> dataset.Leakage:
        return dataset.check_leakage(prompts.PROMPTS[version].full_system(), self.dev, self.held,
                                     self.policy["leakage_containment"])

    def gate(self, baseline: str, candidate: str) -> gate.GateResult:
        return gate.evaluate_gate(self.policy, self.pin, self.leakage(candidate.split(":")[1]), self.held,
                                  self.records(baseline), self.records(candidate))


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


pts = gate.points


# ------------------------------------------------------------------ reports

def report_gate(s: Suite, baseline: str, candidate: str) -> tuple[str, int]:
    g = s.gate(baseline, candidate)
    lines = [f"Gate `{s.policy['policy']}`: {candidate} against {baseline}, "
             f"{len(s.held)} held-out tickets x {s.repeats} runs", "",
             "| Rule | Result | Detail |", "| --- | --- | --- |"]
    lines += [f"| {r.name} | {r.status.upper()} | {r.detail} |" for r in g.rules]
    lines += ["", f"Decision: **{g.decision.upper()}**"]
    return "\n".join(lines), 0 if g.decision == "pass" else 1


def report_candidates(s: Suite) -> str:
    base = runner.summarise(s.records(BASELINE))
    lines = [f"Baseline {BASELINE}: {pct(base.accuracy)} fully correct, cost per correct answer "
             f"${base.cost_per_correct_usd:.6f}", "",
             "| Candidate | Fully correct | Difference (points) | 95% paired interval | Worse / better | "
             "Decision | Failed rules | Warnings | Cost per correct (USD) |",
             "| --- | ---: | ---: | --- | ---: | --- | --- | --- | ---: |"]
    for spec in CANDIDATES:
        g = s.gate(BASELINE, spec)
        c, sm = g.overall, runner.summarise(s.records(spec))
        failed = ", ".join(r.name for r in g.rules if r.status == "fail") or "none"
        warned = ", ".join(r.name for r in g.rules if r.status == "warn") or "none"
        lines.append(f"| {spec} | {pct(sm.accuracy)} | {pts(c.diff)} | {pts(c.low)} to {pts(c.high)} | "
                     f"{c.worse} / {c.better} | {g.decision.upper()} | {failed} | {warned} | "
                     f"{sm.cost_per_correct_usd:.6f} |")
    return "\n".join(lines)


def report_incident(s: Suite) -> str:
    demo = [t for t in s.tickets if t["demo"]]
    d1 = s.records("sim-large:triage-v1", demo, 1)
    d2 = s.records("sim-large:triage-v2", demo, 1)
    prod = {t["id"] for t in s.held if t["source"] == "production"}
    v1, v2 = s.records("sim-large:triage-v1"), s.records("sim-large:triage-v2")
    over = {t["id"] for t in s.held if t["source"] == "production" and t["kind"] == "overstated"}
    g = s.gate("sim-large:triage-v1", "sim-large:triage-v2")
    failed = [r.name for r in g.rules if r.status == "fail"]
    return "\n".join([
        "What the engineer checked: the five sales-demo tickets, one run each",
        f"  triage-v1 {sum(r.correct for r in d1)} of {len(d1)} correct; "
        f"triage-v2 {sum(r.correct for r in d2)} of {len(d2)} correct",
        f"What production saw: held-out tickets sampled from production (n={len(prod)}, {s.repeats} runs)",
        f"  triage-v1 {pct(runner.accuracy_on(v1, prod))}; triage-v2 {pct(runner.accuracy_on(v2, prod))}",
        f"  of which overstated (n={len(over)}): triage-v1 {pct(runner.accuracy_on(v1, over))}; "
        f"triage-v2 {pct(runner.accuracy_on(v2, over))}",
        f"What the gate says: {g.decision.upper()} on {', '.join(failed)}",
    ])


def report_leakage(s: Suite) -> str:
    v1, v3 = s.leakage("triage-v1"), s.leakage("triage-v3")
    hits = {h for h, _ in v3.prompt_hits}
    keep = [t for t in s.held if t["id"] not in hits]
    base, cand = s.records(BASELINE), s.records("sim-large:triage-v3")
    all_c = gate.compare(base, cand, s.held)
    clean_c = gate.compare(base, cand, keep)
    rdev, rheld = dataset.row_split(s.tickets, len(s.dev) - 40)
    row = dataset.check_leakage("", rdev, rheld, s.policy["leakage_containment"])
    fam = dataset.check_leakage("", [t for t in s.dev if t["source"] != "chapter-2"], s.held,
                                s.policy["leakage_containment"])
    ch2 = [t for t in s.dev if t["source"] == "chapter-2"]
    lines = [
        f"Family split (as shipped): {len(v1.family_overlap)} families in both splits; "
        f"{len(v1.cross_split)} held-out tickets with a near-duplicate in dev",
        f"triage-v1 prompt: {len(v1.prompt_hits)} held-out tickets found in it",
        f"triage-v3 prompt: {len(v3.prompt_hits)} held-out tickets found in it: "
        + ", ".join(f"{h} ({c:.2f})" for h, c in v3.prompt_hits),
        f"  triage-v3 against triage-v1, all {all_c.tickets} held-out tickets: {pts(all_c.diff)} points "
        f"({pts(all_c.low)} to {pts(all_c.high)})",
        f"  excluding the {len(hits)} leaked tickets ({clean_c.tickets} left): {pts(clean_c.diff)} points "
        f"({pts(clean_c.low)} to {pts(clean_c.high)})",
        f"Row split instead (generated tickets shuffled and cut at {len(rdev)}): {len(row.family_overlap)} families "
        f"in both splits; {len(row.cross_split)} of {len(rheld)} held-out tickets have a near-duplicate in dev "
        f"(family split: {len(fam.cross_split)} of {len(s.held)})",
    ]
    def router_on(d, h):
        r = router.train(d)
        thr = router.choose_threshold(router.out_of_fold_scores(d), [t["difficulty"] == "hard" for t in d],
                                      ROUTER_RECALL)
        return router.evaluate(r, thr, h)

    fam_ev = router_on(s.dev, s.held)
    n_hard = sum(t["difficulty"] == "hard" for t in s.held)
    caught = round(fam_ev.hard_recall * n_hard)
    lo, hi = stats.wilson_interval(caught, n_hard)
    lines.append(f"Router trained on the family split: held-out hard recall {pct(fam_ev.hard_recall)} "
                 f"({caught} of {n_hard}; Wilson 95% {pct(lo)} to {pct(hi)})")
    recalls, dups = [], []
    for seed in ROW_SEEDS:
        d, h = dataset.row_split(s.tickets, len(s.dev) - 40, seed)
        recalls.append(router_on(d + ch2, h).hard_recall)
        dups.append(len(dataset.check_leakage("", d, h, s.policy["leakage_containment"]).cross_split))
    mean = sum(recalls) / len(recalls)
    sd = (sum((x - mean) ** 2 for x in recalls) / (len(recalls) - 1)) ** 0.5
    lines.append(f"Router trained on row splits, seeds {ROW_SEEDS[0]}-{ROW_SEEDS[-1]}: held-out hard recall "
                 f"mean {pct(mean)}, SD {sd * 100:.1f} points, range {pct(min(recalls))} to {pct(max(recalls))}; "
                 f"inflation over the family split {(mean - fam_ev.hard_recall) * 100:+.1f} points on average")
    lines.append(f"  held-out tickets with a near-duplicate in dev, across those row splits: "
                 f"mean {sum(dups) / len(dups):.1f}, range {min(dups)} to {max(dups)} of {len(s.held)}")
    return "\n".join(lines)


def report_router(s: Suite) -> str:
    r, thr = s.router()
    dev_in = router.evaluate(r, thr, s.dev)
    held = router.evaluate(r, thr, s.held)
    lines = [f"Router: naive Bayes scorecard, {len(r.weights)} features, trained on {len(s.dev)} dev tickets; "
             f"threshold {thr:.3f} chosen for {ROUTER_RECALL:.0%} out-of-fold recall of hard dev tickets", "",
             "| Measure | Dev (training data) | Held-out |", "| --- | ---: | ---: |",
             f"| Hard tickets caught (recall) | {pct(dev_in.hard_recall)} | {pct(held.hard_recall)} |",
             f"| Hard tickets sent to the small model | {dev_in.hard_to_small} | {held.hard_to_small} |",
             f"| Easy tickets sent to the small model | {pct(dev_in.easy_routed)} | {pct(held.easy_routed)} |",
             f"| All tickets sent to the small model | {pct(dev_in.routed_small)} | {pct(held.routed_small)} |", ""]
    for lang in ("en", "es", "de"):
        sub = [t for t in s.held if t["language"] == lang]
        ev = router.evaluate(r, thr, sub)
        n_hard = sum(t["difficulty"] == "hard" for t in sub)
        lines.append(f"Held-out {lang}: hard recall {pct(ev.hard_recall)} of {n_hard} hard tickets")
    base, rt = runner.summarise(s.records(BASELINE)), runner.summarise(s.records("routed:triage-v1"))
    g = s.gate(BASELINE, "routed:triage-v1")
    lines += ["",
              f"Routed (sim-small for predicted-easy, fallback to sim-large on invalid output) against all-sim-large:",
              f"  calls served: {rt.served}; fully correct {pct(base.accuracy)} -> {pct(rt.accuracy)}",
              f"  cost per call ${base.cost_per_call_usd:.6f} -> ${rt.cost_per_call_usd:.6f} "
              f"({(rt.cost_per_call_usd / base.cost_per_call_usd - 1) * 100:+.1f}%); "
              f"cost per correct ${base.cost_per_correct_usd:.6f} -> ${rt.cost_per_correct_usd:.6f}",
              f"  gate: {g.decision.upper()}"]
    lines += [f"    {r_.status.upper()} {r_.name}: {r_.detail}" for r_ in g.rules
              if r_.name.startswith(("regression", "slice")) and r_.status != "pass" or r_.name == "regression"]
    return "\n".join(lines)


def report_stats(s: Suite) -> str:
    base = s.records(BASELINE)
    n_calls = len(base)
    correct = sum(r.correct for r in base)
    lo, hi = stats.wilson_interval(correct, n_calls)
    per_run = []
    for run in range(1, s.repeats + 1):
        rs = [r for r in base if r.run == run]
        per_run.append(sum(r.correct for r in rs) / len(rs))
    lines = [f"Baseline {BASELINE} on {len(s.held)} held-out tickets:",
             "  single runs: " + ", ".join(f"run {i} {pct(a)}" for i, a in enumerate(per_run, 1)),
             f"  all {n_calls} calls: {pct(correct / n_calls)}, Wilson 95% {pct(lo)} to {pct(hi)} "
             f"(treats calls as independent)"]
    for reps in (1, s.repeats):
        rs = [r for r in base if r.run <= reps]
        scores = runner.per_ticket(rs)
        m, l, h = stats.paired_bootstrap([scores[t["id"]] for t in s.held])
        lines.append(f"  resampling tickets, {reps} run(s) each: {pct(m)}, 95% {pct(l)} to {pct(h)} "
                     f"(width {(h - l) * 100:.1f} points)")
    scores = runner.per_ticket(base)
    fams: dict[str, list[float]] = {}
    for t in sorted(s.held, key=lambda t: t["id"]):
        fams.setdefault(t["family"], []).append(scores[t["id"]])
    m, l, h = stats.cluster_bootstrap([fams[k] for k in sorted(fams)])
    lines.append(f"  resampling families ({len(fams)}), {s.repeats} runs each: {pct(m)}, 95% {pct(l)} to {pct(h)} "
                 f"(width {(h - l) * 100:.1f} points)")
    cand = s.records("sim-large:triage-v1.1")
    cc = sum(r.correct for r in cand)
    clo, chi = stats.wilson_interval(cc, len(cand))
    c = gate.compare(base, cand, s.held)
    ct = gate.compare(base, cand, s.held, by="ticket")
    lines += ["", "triage-v1.1 against triage-v1:",
              f"  unpaired: {pct(correct / n_calls)} ({pct(lo)} to {pct(hi)}) vs {pct(cc / len(cand))} "
              f"({pct(clo)} to {pct(chi)})",
              f"  paired, resampling families: difference {pts(c.diff)} points, 95% {pts(c.low)} to {pts(c.high)}; "
              f"{c.worse} worse, {c.better} better, McNemar {gate.p_text(c.p_value)}",
              f"  paired, resampling tickets: 95% {pts(ct.low)} to {pts(ct.high)}"]
    v2 = s.records("sim-large:triage-v2")
    f2, t2 = gate.compare(base, v2, s.held), gate.compare(base, v2, s.held, by="ticket")
    lines += [f"triage-v2 against triage-v1: resampling families {pts(f2.low)} to {pts(f2.high)}; "
              f"resampling tickets {pts(t2.low)} to {pts(t2.high)}"]
    routed = gate.compare(base, s.records("routed:triage-v1"), s.held)
    psi = (routed.worse + routed.better) / routed.tickets
    lines += ["", "Sample size (80% power, two-sided 5%; valid only for differences smaller than the disagreement rate):",
              f"  at the routed system's disagreement rate, {routed.worse + routed.better} of {routed.tickets} "
              f"= {pct(psi)}:"]
    for d in (0.02, 0.03, 0.04):
        lines.append(f"    to detect a {d * 100:.0f}-point difference: {stats.paired_sample_size(psi, d)} tickets")
    lines.append("  at a disagreement rate of 10.0%:")
    for d in (0.02, 0.03, 0.05):
        lines.append(f"    to detect a {d * 100:.0f}-point difference: {stats.paired_sample_size(0.10, d)} tickets")
    return "\n".join(lines)


def report_noise(s: Suite) -> str:
    """The gate's false-alarm rate: the baseline against re-seeded copies of itself."""
    base = s.records(BASELINE)
    fails, by_rule, margin_fails = 0, {}, 0
    for seed in NOISE_SEEDS:
        m = models.SimulatedTriageModel("sim-large", "triage-v1", s.gold, seed=seed)
        cand = runner.run_candidate(f"{BASELINE}#seed{seed}", m, prompts.PROMPTS["triage-v1"], s.held, s.repeats)
        g = gate.evaluate_gate(s.policy, s.pin, s.leakage("triage-v1"), s.held, base, cand)
        failed = [r.name for r in g.rules if r.status == "fail"]
        fails += bool(failed)
        for name in failed:
            by_rule[name] = by_rule.get(name, 0) + 1
        margin_fails += g.overall.low * 100 < -s.policy["regression_margin_points"]
    n = len(NOISE_SEEDS)
    lo, hi = stats.wilson_interval(fails, n)
    rules = ", ".join(f"{k} {v}" for k, v in sorted(by_rule.items())) or "none"
    return "\n".join([
        f"False alarms: {BASELINE} gated against {n} re-seeded copies of itself (same configured behaviour, "
        f"new random draws; SIMULATED)",
        f"  gate failed {fails} of {n} ({pct(fails / n)}; Wilson 95% {pct(lo)} to {pct(hi)})",
        f"  failures by rule: {rules}",
        f"  the margin branch alone (loss over {s.policy['regression_margin_points']:g} points not ruled out): "
        f"{margin_fails} of {n}",
    ])


def report_agents(s: Suite) -> str:
    tasks = agent_eval.load_tasks(s.data / "agent-tasks.jsonl")
    e = agent_eval.evaluate(tasks)
    return "\n".join([
        f"Instruction-file evaluation (SIMULATED agent): {e.tasks} tasks x {e.repeats} runs per condition",
        "| Condition | Runs passing all three checks | Runs breaking a boundary |", "| --- | ---: | ---: |",
        *[f"| {c} | {pct(e.pass_rate[c])} | {e.boundary_violations[c]} of {e.tasks * e.repeats} |"
          for c in agent_eval.CONDITIONS],
        "",
        f"Paired difference (agents-md minus no-instructions): {pts(e.diff)} points, "
        f"95% {pts(e.low)} to {pts(e.high)}; tasks worse {e.worse}, better {e.better} "
        f"(majority of runs), McNemar {gate.p_text(e.p_value)}",
    ])


def report_dataset(s: Suite) -> str:
    import json
    m = json.loads((s.data / "manifest.json").read_text(encoding="utf-8"))
    return "\n".join([
        f"{m['name']} {m['version']}: {m['tickets']} tickets, dev {m['splits']['dev']} "
        f"({m['families']['dev']} families), held-out {m['splits']['heldout']} ({m['families']['heldout']} families)",
        f"Pin check: {'OK' if s.pin.ok else 'FAILED'} ({s.pin.detail})",
        "Held-out by kind: " + ", ".join(f"{k} {v}" for k, v in m["by_kind"]["heldout"].items()),
        "Held-out by language: " + ", ".join(f"{k} {v}" for k, v in m["by_language"]["heldout"].items()),
        "Held-out by source: " + ", ".join(f"{k} {v}" for k, v in m["by_source"]["heldout"].items()),
        f"Labellers agreed before adjudication: {m['labeller_agreement_before_adjudication']:.1%}",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relay triage eval suite (Lab 7.1)")
    ap.add_argument("--data", type=Path, required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate", help="run the regression gate; exit 1 on fail")
    g.add_argument("--baseline", default=BASELINE)
    g.add_argument("--candidate", required=True)
    g.add_argument("--live", action="store_true", help="call real Claude models (costs money)")
    g.add_argument("--max-usd", type=float, default=0.0, help="spend ceiling for a live run")
    for name in ("candidates", "incident", "leakage", "router", "stats", "agents", "dataset", "noise"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to a legacy code page

    if args.cmd == "gate":
        if args.live and args.max_usd <= 0:
            print("a live run needs --max-usd", file=sys.stderr)
            return 2
        s = Suite(args.data, live=args.live, max_usd=args.max_usd)
        text, code = report_gate(s, args.baseline, args.candidate)
        print(text)
        return code
    s = Suite(args.data)
    print({"candidates": report_candidates, "incident": report_incident, "leakage": report_leakage,
           "router": report_router, "stats": report_stats, "agents": report_agents,
           "dataset": report_dataset, "noise": report_noise}[args.cmd](s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
