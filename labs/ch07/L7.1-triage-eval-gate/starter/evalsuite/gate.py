"""The regression gate: compare a candidate with the baseline on the pinned held-out set (STARTER: implement the TODO functions)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import stats
from .dataset import Leakage, Pin, slices_of
from .runner import Record, majority, per_ticket, summarise


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


def evaluate_gate(policy: dict, pin: Pin, leakage: Leakage, tickets: list[dict],
                  baseline: list[Record], candidate: list[Record]) -> GateResult:
    """Apply the policy's rules, in this order, and return every rule's outcome.

    tickets are the held-out tickets; baseline and candidate are their records.
    Points are percentage points (a proportion times 100).

    1. dataset   fail unless pin.ok.
    2. leakage   fail if leakage.prompt_hits is non-empty (held-out text in the prompt).
    3. complete  fail if any candidate or baseline record has error "budget",
                 or the candidate lacks policy["repeats"] runs for some ticket.
    4. schema    fail if the candidate's schema-valid share < policy["min_schema_valid"].
    5. floor     fail if the candidate's accuracy over all calls < policy["min_accuracy"].
    6. regression  compare() on all tickets. fail if high < 0 (worse beyond noise),
                 or if low * 100 < -policy["regression_margin_points"] (a larger drop
                 cannot be ruled out). Otherwise pass.
    7. injection fail if the candidate's injection_obeyed / injection_calls >
                 policy["max_injection_rate"] (0 when there are no injected calls).
    8. cost      warn if the candidate's cost per correct answer exceeds the baseline's
                 by more than policy["cost_warn_increase"] (0.25 means 25%); else pass.
    9. one rule per slice in policy["slices"], named "slice <name>": compare() on the
                 slice's tickets. fail if high < 0; else warn if -diff * 100 >
                 policy["slice_warn_drop_points"]; else pass.

    decision is "fail" if any rule failed, else "pass". Warnings never fail the
    gate; a reviewer must acknowledge them. Every rule is evaluated even after
    a failure, so the report shows everything that is wrong. Use the policy's
    bootstrap settings for every compare() call.
    """
    # TODO(L7.1): implement using the definition in the docstring.
    raise NotImplementedError("evaluate_gate")


def points(x: float) -> str:
    """A proportion as signed percentage points, one decimal, never "-0.0"."""
    return f"{round(x * 100, 1) + 0.0:+.1f}"


def _interval(c: Comparison) -> str:
    return (f"{c.baseline_accuracy:.1%} -> {c.candidate_accuracy:.1%}, difference {points(c.diff)} points "
            f"(95% paired interval {points(c.low)} to {points(c.high)}); "
            f"{c.worse} worse, {c.better} better, McNemar p={c.p_value:.3f}")
