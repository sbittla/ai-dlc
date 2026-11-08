"""Run a judge over human-labelled answers and pairs, and measure it (reference solution)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import metrics


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass(frozen=True)
class Calibration:
    judge: str
    split: str
    items: int
    confusion: metrics.Confusion
    kappa: float
    kappa_ci: tuple[float, float]
    human_kappa: float                # labeller A against labeller B: the ceiling
    false_pass: dict[str, float]      # by probe group
    false_pass_n: dict[str, int]
    pairs: int
    first_position_rate: float        # share of single-order verdicts that chose position A
    swap_consistency: float
    pair_accuracy: float              # single order, against the human preference
    both_orders_decided: float        # share of pairs where both orders agree
    both_orders_accuracy: float       # accuracy on those pairs

    @property
    def verbosity_gap(self) -> float:
        return self.false_pass["verbose"] - self.false_pass["concise"]

    @property
    def self_preference_gap(self) -> float:
        return self.false_pass["own family"] - self.false_pass["other family"]


def calibrate(judge, answers: list[dict], pairs: list[dict], split: str) -> Calibration:
    items = [a for a in answers if a["split"] == split]
    verdicts = [judge.grade(a) for a in items]
    human = [a["human"] for a in items]
    conf = metrics.confusion(human, verdicts)
    kappa = metrics.cohen_kappa(human, verdicts)

    wrong = [(a, v) for a, v in zip(items, verdicts) if a["human"] == "fail"]
    groups = {
        "concise": lambda a: a["style"] == "concise",
        "verbose": lambda a: a["style"] == "verbose",
        "own family": lambda a: a["source_family"] == "large",
        "other family": lambda a: a["source_family"] != "large",
    }
    fp, fp_n = {}, {}
    for name, test in groups.items():
        sub = [v for a, v in wrong if test(a)]
        fp_n[name] = len(sub)
        fp[name] = sum(v != "fail" for v in sub) / len(sub)

    by_id = {a["id"]: a for a in answers}
    ps = [p for p in pairs if p["split"] == split]
    ab, ba = [], []
    for p in ps:
        a, b = by_id[p["a"]], by_id[p["b"]]
        ab.append(judge.prefer(p["id"], "ab", a, b))
        ba.append(judge.prefer(p["id"], "ba", b, a))
    truth = [p["human_preferred"] for p in ps]
    decided = [(x, t) for x, y, t in zip(ab, ba, truth) if x is not None and y is not None and x != y]
    return Calibration(
        judge=judge.name, split=split, items=len(items), confusion=conf, kappa=kappa,
        kappa_ci=metrics.kappa_interval(human, verdicts),
        human_kappa=metrics.cohen_kappa([a["labeller_a"] for a in items], [a["labeller_b"] for a in items]),
        false_pass=fp, false_pass_n=fp_n, pairs=len(ps),
        first_position_rate=sum(v == "A" for v in ab + ba) / (2 * len(ps)),
        swap_consistency=metrics.swap_consistency(ab, ba),
        pair_accuracy=sum(v == t for v, t in zip(ab, truth)) / len(ps),
        both_orders_decided=len(decided) / len(ps),
        both_orders_accuracy=sum(x == t for x, t in decided) / len(decided) if decided else 0.0,
    )
