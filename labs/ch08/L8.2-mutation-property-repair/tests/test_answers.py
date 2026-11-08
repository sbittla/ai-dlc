"""The arithmetic in book/answers/ch08-answers.md (Exercise 6), checked with the lab's score."""

import math

import pytest

from mutate.score import Score, gate


def test_exercise_6_score_with_and_without_the_equivalence_claim():
    claimed = Score("m", mutants=140, killed=112, survived=14, not_covered=8, equivalent=6)
    assert claimed.score == pytest.approx(112 / 134) and round(claimed.score * 100, 1) == 83.6
    assert round(claimed.raw * 100, 1) == 80.0
    assert gate([claimed], 0.9) == ["m: 83.6% is below 90%"]


def test_exercise_6_kills_needed_to_reach_90_percent():
    needed = math.ceil(0.9 * (140 - 6)) - 112
    assert needed == 9
    assert gate([Score("m", 140, 112 + needed, 14 - needed, 8, 6)], 0.9) == []
    assert gate([Score("m", 140, 112 + needed - 1, 15 - needed, 8, 6)], 0.9) != []


def test_exercise_6_calling_the_uncovered_mutants_equivalent_still_fails():
    generous = Score("m", 140, 112, 14, 0, 14)
    assert round(generous.score * 100, 1) == 88.9 and gate([generous], 0.9) != []
