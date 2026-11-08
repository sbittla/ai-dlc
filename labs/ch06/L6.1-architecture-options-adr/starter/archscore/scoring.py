"""Weighted scoring of architecture options against drivers.

TODO 1-3 are yours in starter/: weighted_score, rank and weight_to_flip.
The arithmetic is deliberately simple. The value of the tool is that every
weight and every score is written down with a reason, the same inputs always
give the same ranking, and the sensitivity check says how fragile it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MAX_SCORE, Driver, Option
from .structure import deployables


@dataclass(frozen=True)
class Total:
    total: int
    maximum: int

    @property
    def percent(self) -> float:
        return round(100 * self.total / self.maximum, 1) if self.maximum else 0.0


@dataclass(frozen=True)
class Ranked:
    option_id: str
    total: Total
    disqualified: tuple[str, ...]   # IDs of must drivers the option scores 0 on
    deployables: int


def weighted_score(option: Option, drivers: tuple[Driver, ...] | list[Driver]) -> Total:
    """TODO 1. Sum weight x score over drivers with weight > 0.

    `maximum` is the sum of weight x MAX_SCORE over the same drivers. Drivers with
    weight 0 are ignored, scored or not. Raise KeyError if the option has no score
    for a driver with weight > 0, and ValueError if a score is outside 0..MAX_SCORE.
    """
    raise NotImplementedError("TODO 1: weighted_score")


def disqualifiers(option: Option, drivers) -> tuple[str, ...]:
    """Must drivers (with weight > 0) on which the option scores 0, in catalogue order. Provided."""
    return tuple(d.id for d in drivers if d.must and d.weight > 0 and option.scores[d.id].value == 0)


def rank(options: list[Option], drivers) -> list[Ranked]:
    """TODO 2. Rank options, best first.

    Qualified options (no disqualifiers) come before disqualified ones. Within each
    group: higher total first; on equal totals, fewer deployable units first (the
    simpler option wins a tie); then option ID. Use `disqualifiers` and
    `structure.deployables`.
    """
    raise NotImplementedError("TODO 2: rank")


def weight_to_flip(leader: Option, runner_up: Option, drivers, lo: int = 0, hi: int = 5) -> dict[str, int | None]:
    """TODO 3. For each driver, the nearest weight in lo..hi that makes `runner_up` win.

    Change one driver's weight at a time, keeping every other weight. "Win" means the
    runner-up's weighted total is strictly greater than the leader's. Search weights
    in order of distance from the driver's current weight; at equal distance try the
    lower weight first. Return {driver id: weight, or None if no weight in lo..hi
    flips the ranking}, for every driver in catalogue order.
    """
    raise NotImplementedError("TODO 3: weight_to_flip")


def score_changes_to_flip(leader: Option, runner_up: Option, drivers) -> tuple[int, int]:
    """(gap, n): the fewest one-point score changes that would make `runner_up` win. Provided.

    A one-point change either raises one of the runner-up's scores or lowers one of the
    leader's, on a driver with weight > 0, within 0..MAX_SCORE. Each is worth the driver's
    weight; taking the heaviest first gives the fewest changes. n is None if no set of
    changes is enough.
    """
    gap = weighted_score(leader, drivers).total - weighted_score(runner_up, drivers).total
    steps = []
    for d in drivers:
        if d.weight <= 0:
            continue
        steps += [d.weight] * (MAX_SCORE - runner_up.scores[d.id].value)
        steps += [d.weight] * leader.scores[d.id].value
    gained = 0
    for n, w in enumerate(sorted(steps, reverse=True), 1):
        gained += w
        if gained > gap:
            return gap, n
    return gap, None


def head_to_head(a: Option, b: Option, drivers) -> dict[str, list[str]]:
    """Which significant drivers each option scores higher on, and the ties. Provided."""
    out: dict[str, list[str]] = {a.id: [], b.id: [], "equal": [], "not significant": []}
    for d in drivers:
        if d.weight <= 0:
            out["not significant"].append(d.id)
            continue
        sa, sb = a.scores[d.id].value, b.scores[d.id].value
        out[a.id if sa > sb else b.id if sb > sa else "equal"].append(d.id)
    return out
