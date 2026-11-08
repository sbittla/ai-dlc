"""Hand-checkable fixtures for agreement metrics (metrics.py)."""

import pytest

from judgecal import metrics

P, F = "pass", "fail"


# ------------------------------------------------------------ confusion

def test_confusion_by_hand():
    human = [P, P, F, F, P, F]
    judge = [P, F, P, F, None, None]
    c = metrics.confusion(human, judge)
    assert (c.tp, c.fp, c.fn, c.tn, c.none) == (1, 2, 2, 1, 2)   # a missing verdict is never agreement
    assert c.n == 6
    assert c.accuracy == pytest.approx(2 / 6)
    assert c.false_pass_rate == pytest.approx(2 / 3)


def test_confusion_rejects_mismatched_lists():
    with pytest.raises(ValueError):
        metrics.confusion([P], [P, F])
    with pytest.raises(ValueError):
        metrics.confusion([], [])


# ------------------------------------------------------------ cohen_kappa

def test_kappa_by_hand():
    a = [P, P, P, F, F, F, P, F, P, P]
    b = [P, P, F, F, F, P, P, F, P, F]
    # p_o = 7/10; p_e = 0.6 * 0.5 + 0.4 * 0.5 = 0.5; kappa = (0.7 - 0.5) / 0.5
    assert metrics.cohen_kappa(a, b) == pytest.approx(0.4)


def test_kappa_treats_no_verdict_as_its_own_label():
    # p_o = 3/4; p_e = 0.5*0.75 + 0.25*0.25 + 0.25*0 = 0.4375
    assert metrics.cohen_kappa([P, F, None, P], [P, F, P, P]) == pytest.approx((0.75 - 0.4375) / 0.5625)


@pytest.mark.parametrize("a, b, expected", [
    ([P, P], [P, P], 1.0),        # one label throughout: defined as perfect agreement
    ([P, F], [F, P], -1.0),       # systematic disagreement
    ([P, F, P, F], [P, F, P, F], 1.0),
])
def test_kappa_edges(a, b, expected):
    assert metrics.cohen_kappa(a, b) == pytest.approx(expected)


def test_kappa_is_not_accuracy():
    # 90% raw agreement, but only because both raters say "pass" almost always.
    a = [P] * 9 + [F]
    b = [P] * 10
    assert metrics.cohen_kappa(a, b) == pytest.approx(0.0)


# ------------------------------------------------------------ swap_consistency

def test_swap_consistency_by_hand():
    # Same answer in both orders means the letters differ: A then B, or B then A.
    assert metrics.swap_consistency(["A", "B", "A", None], ["B", "B", "A", "A"]) == pytest.approx(0.25)


def test_swap_consistency_rejects_mismatched_lists():
    with pytest.raises(ValueError):
        metrics.swap_consistency(["A"], [])


def test_kappa_interval_is_reproducible_and_brackets_the_estimate():
    a = [P, P, P, F, F, F, P, F, P, P] * 3
    b = [P, P, F, F, F, P, P, F, P, F] * 3
    lo, hi = metrics.kappa_interval(a, b, 500, 7)
    assert (lo, hi) == metrics.kappa_interval(a, b, 500, 7)
    assert lo <= metrics.cohen_kappa(a, b) <= hi
