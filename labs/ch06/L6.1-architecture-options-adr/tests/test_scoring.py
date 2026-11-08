"""Specification tests for TODO 1-3 (archscore/scoring.py), on inputs small enough to check by hand."""

import pytest

from archscore.model import Component, Driver, Option, Score
from archscore.scoring import rank, weight_to_flip, weighted_score


def drv(id_, weight, must=False):
    return Driver(id_, "nfr", "x", id_, weight, must, "test")


def opt(id_, scores, deployables=1):
    comps = tuple(Component(f"p{i}", f"p{i}", "process", f"unit{i}") for i in range(deployables))
    return Option(id_, id_, "", comps, (), {}, (), {k: Score(v, "") for k, v in scores.items()})


DRIVERS = (drv("X", 3), drv("Y", 1), drv("Z", 0))


# ------------------------------------------------------------ TODO 1: weighted_score

def test_weighted_total_and_maximum():
    # X: 3 x 2 = 6; Y: 1 x 3 = 3; Z has weight 0 and is ignored. Maximum: (3 + 1) x 3 = 12.
    t = weighted_score(opt("A", {"X": 2, "Y": 3, "Z": 0}), DRIVERS)
    assert (t.total, t.maximum, t.percent) == (9, 12, 75.0)


def test_weight_zero_driver_needs_no_score():
    assert weighted_score(opt("A", {"X": 1, "Y": 1}), DRIVERS).total == 4


def test_missing_score_for_a_weighted_driver_is_an_error():
    with pytest.raises(KeyError):
        weighted_score(opt("A", {"X": 1}), DRIVERS)


@pytest.mark.parametrize("bad", [-1, 4])
def test_score_outside_scale_is_an_error(bad):
    with pytest.raises(ValueError):
        weighted_score(opt("A", {"X": bad, "Y": 1}), DRIVERS)


# ------------------------------------------------------------ TODO 2: rank

def test_higher_total_ranks_first():
    r = rank([opt("A", {"X": 1, "Y": 1}), opt("B", {"X": 3, "Y": 0})], DRIVERS)
    assert [x.option_id for x in r] == ["B", "A"] and r[0].total.total == 9


def test_a_tie_goes_to_the_option_with_fewer_deployable_units():
    a = opt("A", {"X": 2, "Y": 0}, deployables=5)
    b = opt("B", {"X": 2, "Y": 0}, deployables=1)
    assert [x.option_id for x in rank([a, b], DRIVERS)] == ["B", "A"]


def test_full_tie_goes_by_option_id():
    a, b = opt("A", {"X": 2, "Y": 0}), opt("B", {"X": 2, "Y": 0})
    assert [x.option_id for x in rank([b, a], DRIVERS)] == ["A", "B"]


def test_a_must_driver_scored_zero_disqualifies_whatever_the_total():
    drivers = (drv("X", 3, must=True), drv("Y", 5))
    fast_but_fails = opt("C", {"X": 0, "Y": 3})       # 15 points, but fails a must
    modest = opt("A", {"X": 1, "Y": 0})                # 3 points
    r = rank([fast_but_fails, modest], drivers)
    assert [x.option_id for x in r] == ["A", "C"]
    assert r[1].disqualified == ("X",) and r[1].total.total == 15


# ------------------------------------------------------------ TODO 3: weight_to_flip

def test_flip_weights_by_hand():
    # Leader A: X 3, Y 1 -> 3x3 + 1x1 = 10. Runner-up B: X 1, Y 3 -> 3x1 + 1x3 = 6. Gap 4.
    # Raising Y (where B leads by 2) to w gives A 9 + w, B 3 + 3w: B wins when 2w > 6, so w = 4.
    # Lowering X (where A leads by 2) to w gives A 3w + 1, B w + 3: B wins when w < 1, so w = 0.
    # Z: both score 0 there, so no weight changes anything.
    a = opt("A", {"X": 3, "Y": 1, "Z": 0})
    b = opt("B", {"X": 1, "Y": 3, "Z": 0})
    assert weight_to_flip(a, b, DRIVERS) == {"X": 0, "Y": 4, "Z": None}


def test_flip_needs_strictly_greater_and_respects_the_range():
    # A: 2x2 + 1x0 = 4. B: 2x1 + 1x1 = 3. Gap 1.
    # Y at 2 gives A 4, B 4: a tie is not a win. Y at 3 gives B 5. X at 1 ties; X at 0 gives A 0, B 1.
    drivers = (drv("X", 2), drv("Y", 1))
    a, b = opt("A", {"X": 2, "Y": 0}), opt("B", {"X": 1, "Y": 1})
    assert weight_to_flip(a, b, drivers) == {"X": 0, "Y": 3}
    assert weight_to_flip(a, b, drivers, lo=1, hi=2) == {"X": None, "Y": None}


def test_nearest_flipping_weight_is_reported():
    # A: 1x3 + 2x0 = 3. B: 1x0 + 2x1 = 2. X at 0 flips (A 0, B 2). Y must reach 4 (A 3, B 4).
    drivers = (drv("X", 1), drv("Y", 2))
    a, b = opt("A", {"X": 3, "Y": 0}), opt("B", {"X": 0, "Y": 1})
    assert weight_to_flip(a, b, drivers) == {"X": 0, "Y": 4}
