"""The regression gate: compare a candidate with the baseline on the pinned held-out set (STARTER: implement the TODO functions)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import stats
from .dataset import Leakage, Pin, slices_of
from .runner import Record, Summary, majority, per_ticket, summarise


def load_policy(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Comparison:
    """Paired comparison of candidate minus baseline on the same tickets."""

    tickets: int
    baseline_accuracy: float
    candidate_accuracy: float
    diff: float           # mean per-ticket difference (candidate - baseline), as a proportion
    low: float            # 95% paired bootstrap interval
    high: float
    worse: int            # McNemar b: baseline right, candidate wrong (majority of runs)
    better: int           # McNemar c: candidate right, baseline wrong
    p_value: float        # exact McNemar


def compare(baseline: list[Record], candidate: list[Record], ticket_ids: list[str],
            resamples: int = 2000, seed: int = 7) -> Comparison:
    ids = sorted(ticket_ids)
    sb, sc = per_ticket(baseline), per_ticket(candidate)
    diffs = [sc[t] - sb[t] for t in ids]
    mean, lo, hi = stats.paired_bootstrap(diffs, resamples, seed)
    mb, mc = majority(baseline), majority(candidate)
    worse = sum(mb[t] and not mc[t] for t in ids)
    better = sum(mc[t] and not mb[t] for t in ids)
    return Comparison(len(ids), sum(sb[t] for t in ids) / len(ids), sum(sc[t] for t in ids) / len(ids),
                      mean, lo, hi, worse, better, stats.mcnemar_exact(worse, better))


@dataclass(frozen=True)
class Rule:
    name: str
    status: str   # "pass", "fail" or "warn"
    detail: str


@dataclass(frozen=True)
class GateResult:
    decision: str  # "pass" or "fail"
    rules: list[Rule] = field(default_factory=list)
    overall: Comparison | None = None


@dataclass(frozen=True)
class Facts:
    """Everything the rules look at, computed once (provided)."""

    pin: Pin
    leakage: Leakage
    budget_stops: int                  # baseline and candidate calls stopped by the budget
    short_tickets: int                 # tickets with fewer candidate runs than the policy's repeats
    baseline: Summary
    candidate: Summary
    overall: Comparison
    slices: dict[str, Comparison]      # slice name -> comparison on that slice's tickets

    @property
    def injection_rate(self) -> float:
        c = self.candidate
        return c.injection_obeyed / c.injection_calls if c.injection_calls else 0.0

    @property
    def cost_ratio(self) -> float:
        return self.candidate.cost_per_correct_usd / self.baseline.cost_per_correct_usd


def gather(policy: dict, pin: Pin, leakage: Leakage, tickets: list[dict],
           baseline: list[Record], candidate: list[Record]) -> Facts:
    boot = policy["bootstrap"]
    runs: dict[str, int] = {}
    for r in candidate:
        runs[r.ticket_id] = runs.get(r.ticket_id, 0) + 1
    ids = [t["id"] for t in tickets]
    slices = {name: compare(baseline, candidate, [t["id"] for t in tickets if name in slices_of(t)],
                            boot["resamples"], boot["seed"]) for name in policy["slices"]}
    return Facts(pin, leakage,
                 budget_stops=sum(r.error == "budget" for r in baseline + candidate),
                 short_tickets=sum(runs.get(i, 0) < policy["repeats"] for i in ids),
                 baseline=summarise(baseline), candidate=summarise(candidate),
                 overall=compare(baseline, candidate, ids, boot["resamples"], boot["seed"]), slices=slices)


def rule_names(policy: dict) -> list[str]:
    return (["dataset", "leakage", "complete", "schema", "floor", "regression", "injection", "cost"]
            + [f"slice {name}" for name in policy["slices"]])


def rule_status(name: str, f: Facts, policy: dict) -> str:
    """Return "pass", "fail" or "warn" for one rule. Points are a proportion times 100.

    dataset     fail unless f.pin.ok.
    leakage     fail if f.leakage.prompt_hits is non-empty (held-out text in the prompt).
    complete    fail if f.budget_stops > 0 or f.short_tickets > 0.
    schema      fail if f.candidate.schema_valid < policy["min_schema_valid"].
    floor       fail if f.candidate.accuracy < policy["min_accuracy"].
    regression  fail if f.overall.high < 0 (worse beyond noise), or if
                f.overall.low * 100 < -policy["regression_margin_points"]
                (a larger drop cannot be ruled out). Otherwise pass.
    injection   fail if f.injection_rate > policy["max_injection_rate"].
    cost        warn if f.cost_ratio - 1 > policy["cost_warn_increase"]; else pass.
    slice <s>   with c = f.slices[s]: fail if c.high < 0; else warn if
                -c.diff * 100 > policy["slice_warn_drop_points"]; else pass.

    Only "cost" and the slice rules can warn. Raise KeyError for an unknown rule.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("rule_status")


def describe(name: str, f: Facts, policy: dict) -> str:
    """The human-readable detail for one rule (provided; the golden reports depend on it)."""
    sc = f.candidate
    if name == "dataset":
        return f.pin.detail
    if name == "leakage":
        hits = f.leakage.prompt_hits
        return f"{len(hits)} held-out tickets found in the prompt" if hits else "no held-out ticket in the prompt"
    if name == "complete":
        if not f.budget_stops and not f.short_tickets:
            return "every planned call has an outcome"
        return f"{f.budget_stops} calls stopped by the budget; {f.short_tickets} tickets short of runs"
    if name == "schema":
        return f"{sc.schema_valid:.1%} schema-valid (minimum {policy['min_schema_valid']:.0%})"
    if name == "floor":
        return f"{sc.accuracy:.1%} fully correct (minimum {policy['min_accuracy']:.0%})"
    if name == "regression":
        o, margin = f.overall, policy["regression_margin_points"]
        if o.high < 0:
            return f"worse beyond noise: {_interval(o)}"
        if o.low * 100 < -margin:
            return f"cannot rule out a drop over {margin:g} points: {_interval(o)}"
        return _interval(o)
    if name == "injection":
        return (f"obeyed {sc.injection_obeyed} of {sc.injection_calls} injected calls "
                f"(maximum {policy['max_injection_rate']:.0%}; baseline {f.baseline.injection_obeyed})")
    if name == "cost":
        return (f"cost per correct answer ${f.baseline.cost_per_correct_usd:.6f} -> "
                f"${sc.cost_per_correct_usd:.6f} ({(f.cost_ratio - 1) * 100:+.0f}%)")
    c = f.slices[name.removeprefix("slice ")]
    return f"n={c.tickets}: {_interval(c)}"


def evaluate_gate(policy: dict, pin: Pin, leakage: Leakage, tickets: list[dict],
                  baseline: list[Record], candidate: list[Record]) -> GateResult:
    """Every rule's outcome, in order (provided). The decision is "fail" if any rule
    failed. Warnings never fail the gate; a named reviewer must acknowledge them."""
    f = gather(policy, pin, leakage, tickets, baseline, candidate)
    rules = [Rule(n, rule_status(n, f, policy), describe(n, f, policy)) for n in rule_names(policy)]
    return GateResult("fail" if any(r.status == "fail" for r in rules) else "pass", rules, f.overall)


def points(x: float) -> str:
    """A proportion as signed percentage points, one decimal, never "-0.0"."""
    return f"{round(x * 100, 1) + 0.0:+.1f}"


def _interval(c: Comparison) -> str:
    return (f"{c.baseline_accuracy:.1%} -> {c.candidate_accuracy:.1%}, difference {points(c.diff)} points "
            f"(95% paired interval {points(c.low)} to {points(c.high)}); "
            f"{c.worse} worse, {c.better} better, McNemar {p_text(c.p_value)}")


def p_text(p: float) -> str:
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"
