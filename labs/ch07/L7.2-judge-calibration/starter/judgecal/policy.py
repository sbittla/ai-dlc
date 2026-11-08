"""When may a judge replace human labels? A written decision rule (STARTER: implement the TODO functions)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .calibrate import Calibration

SINGLE = ["items", "kappa", "human gap", "false pass", "verbosity", "self-preference"]
PAIRWISE = ["pairs", "swap", "accuracy"]


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


def check_results(policy: dict, c: Calibration) -> dict[str, bool]:
    """Whether each check passes, keyed by the names in SINGLE and PAIRWISE.

    items            c.items >= policy["min_items"]
    kappa            c.kappa_ci[0] >= policy["min_kappa_lower"]
    human gap        c.human_kappa - c.kappa <= policy["max_kappa_gap"]
    false pass       c.confusion.false_pass_rate <= policy["max_false_pass_rate"]
    verbosity        c.verbosity_gap * 100 <= policy["max_bias_gap_points"]
    self-preference  c.self_preference_gap * 100 <= policy["max_bias_gap_points"]
    pairs            c.pairs >= policy["min_pairs"]
    swap             c.swap_consistency >= policy["min_swap_consistency"]
    accuracy         c.both_orders_accuracy >= policy["min_pair_accuracy"]
    """
    # TODO(L7.2): implement using the definition in the docstring.
    raise NotImplementedError("check_results")


def describe(name: str, p: dict, c: Calibration) -> str:
    """The human-readable detail for one check (provided; the golden reports depend on it)."""
    k = c.confusion
    return {
        "items": lambda: f"{c.items} human-labelled answers (minimum {p['min_items']})",
        "kappa": lambda: (f"kappa {c.kappa:.2f}, 95% {c.kappa_ci[0]:.2f} to {c.kappa_ci[1]:.2f} "
                          f"(lower bound at least {p['min_kappa_lower']:.2f})"),
        "human gap": lambda: (f"humans agree at kappa {c.human_kappa:.2f}; gap {c.human_kappa - c.kappa:.2f} "
                              f"(at most {p['max_kappa_gap']:.2f})"),
        "false pass": lambda: (f"{k.fp} of {k.fp + k.tn} wrong answers passed ({k.false_pass_rate:.1%}; "
                               f"at most {p['max_false_pass_rate']:.0%})"),
        "verbosity": lambda: (f"false passes: verbose {c.false_pass['verbose']:.1%} vs concise "
                              f"{c.false_pass['concise']:.1%} ({c.verbosity_gap * 100:+.1f} points; "
                              f"at most {p['max_bias_gap_points']:g})"),
        "self-preference": lambda: (f"false passes: own family {c.false_pass['own family']:.1%} vs other "
                                    f"{c.false_pass['other family']:.1%} ({c.self_preference_gap * 100:+.1f} "
                                    f"points; at most {p['max_bias_gap_points']:g})"),
        "pairs": lambda: f"{c.pairs} human-preferred pairs (minimum {p['min_pairs']})",
        "swap": lambda: (f"same answer chosen in both orders for {c.swap_consistency:.1%} "
                         f"(at least {p['min_swap_consistency']:.0%})"),
        "accuracy": lambda: (f"{c.both_orders_accuracy:.1%} agree with humans where both orders agree "
                             f"(at least {p['min_pair_accuracy']:.0%})"),
    }[name]()


def decide(policy: dict, c: Calibration) -> list[Decision]:
    """Two decisions, single grading then pairwise (provided). A use is allowed only if
    every one of its checks passes; otherwise humans stay in the loop for that use."""
    ok = check_results(policy, c)
    out = []
    for use, names in (("single grading", SINGLE), ("pairwise (both orders)", PAIRWISE)):
        checks = [Check(n, bool(ok[n]), describe(n, policy, c)) for n in names]
        out.append(Decision(use, all(x.ok for x in checks), checks))
    return out
