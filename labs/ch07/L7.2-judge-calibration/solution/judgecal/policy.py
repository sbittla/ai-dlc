"""When may a judge replace human labels? A written decision rule (reference solution)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .calibrate import Calibration


def load_policy(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Decision:
    use: str               # "single grading" or "pairwise (both orders)"
    allowed: bool
    checks: list[Check]


def decide(policy: dict, c: Calibration) -> list[Decision]:
    """Apply the policy to one judge's held-out calibration. Returns two decisions, in this order.

    "single grading" is allowed only if every check passes:
      items         c.items >= policy["min_items"]
      kappa         c.kappa_ci[0] >= policy["min_kappa_lower"]
      human gap     c.human_kappa - c.kappa <= policy["max_kappa_gap"]
      false pass    c.confusion.false_pass_rate <= policy["max_false_pass_rate"]
      verbosity     c.verbosity_gap * 100 <= policy["max_bias_gap_points"]
      self-preference  c.self_preference_gap * 100 <= policy["max_bias_gap_points"]

    "pairwise (both orders)" is allowed only if every check passes:
      pairs         c.pairs >= policy["min_pairs"]
      swap          c.swap_consistency >= policy["min_swap_consistency"]
      accuracy      c.both_orders_accuracy >= policy["min_pair_accuracy"]

    Check names are exactly as listed; details are free text. A judge that fails
    a check keeps humans in the loop for that use; it does not fail the build.
    """
    def chk(name, ok, detail):
        return Check(name, bool(ok), detail)

    single = [
        chk("items", c.items >= policy["min_items"], f"{c.items} human-labelled answers (minimum {policy['min_items']})"),
        chk("kappa", c.kappa_ci[0] >= policy["min_kappa_lower"],
            f"kappa {c.kappa:.2f}, 95% {c.kappa_ci[0]:.2f} to {c.kappa_ci[1]:.2f} (lower bound at least {policy['min_kappa_lower']:.2f})"),
        chk("human gap", c.human_kappa - c.kappa <= policy["max_kappa_gap"],
            f"humans agree at kappa {c.human_kappa:.2f}; gap {c.human_kappa - c.kappa:.2f} (at most {policy['max_kappa_gap']:.2f})"),
        chk("false pass", c.confusion.false_pass_rate <= policy["max_false_pass_rate"],
            f"{c.confusion.fp} of {c.confusion.fp + c.confusion.tn} wrong answers passed "
            f"({c.confusion.false_pass_rate:.1%}; at most {policy['max_false_pass_rate']:.0%})"),
        chk("verbosity", c.verbosity_gap * 100 <= policy["max_bias_gap_points"],
            f"false passes: verbose {c.false_pass['verbose']:.1%} vs concise {c.false_pass['concise']:.1%} "
            f"({c.verbosity_gap * 100:+.1f} points; at most {policy['max_bias_gap_points']:g})"),
        chk("self-preference", c.self_preference_gap * 100 <= policy["max_bias_gap_points"],
            f"false passes: own family {c.false_pass['own family']:.1%} vs other {c.false_pass['other family']:.1%} "
            f"({c.self_preference_gap * 100:+.1f} points; at most {policy['max_bias_gap_points']:g})"),
    ]
    pairwise = [
        chk("pairs", c.pairs >= policy["min_pairs"], f"{c.pairs} human-preferred pairs (minimum {policy['min_pairs']})"),
        chk("swap", c.swap_consistency >= policy["min_swap_consistency"],
            f"same answer chosen in both orders for {c.swap_consistency:.1%} (at least {policy['min_swap_consistency']:.0%})"),
        chk("accuracy", c.both_orders_accuracy >= policy["min_pair_accuracy"],
            f"{c.both_orders_accuracy:.1%} agree with humans where both orders agree "
            f"(at least {policy['min_pair_accuracy']:.0%})"),
    ]
    return [Decision("single grading", all(x.ok for x in single), single),
            Decision("pairwise (both orders)", all(x.ok for x in pairwise), pairwise)]
