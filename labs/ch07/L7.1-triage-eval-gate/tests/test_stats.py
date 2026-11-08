"""Hand-checkable fixtures for the paired statistics (stats.py)."""

import pytest

from evalsuite import stats


# ------------------------------------------------------------ mcnemar_exact

@pytest.mark.parametrize("b, c, expected", [
    (1, 7, 2 * (1 + 8) / 256),        # n = 8, lower tail k <= 1
    (0, 5, 2 * 1 / 32),               # every discordant ticket went one way
    (2, 10, 2 * (1 + 12 + 66) / 4096),
    (3, 3, 1.0),                      # balanced: capped at 1
    (0, 0, 1.0),                      # no discordant tickets: no evidence of a difference
])
def test_mcnemar_exact_known_values(b, c, expected):
    assert stats.mcnemar_exact(b, c) == pytest.approx(expected)


def test_mcnemar_is_symmetric_and_rejects_negative_counts():
    assert stats.mcnemar_exact(7, 1) == stats.mcnemar_exact(1, 7)
    with pytest.raises(ValueError):
        stats.mcnemar_exact(-1, 3)


# ------------------------------------------------------------ paired_bootstrap

def test_bootstrap_of_a_constant_is_that_constant():
    assert stats.paired_bootstrap([0.25] * 8, n_resamples=50) == pytest.approx((0.25, 0.25, 0.25))


def test_bootstrap_follows_the_docstring_exactly():
    # Five per-ticket differences, 10 resamples, seed 3: locked so every implementation agrees.
    assert stats.paired_bootstrap([0.0, 1.0, 0.0, -1.0, 0.5], 10, 3) == pytest.approx((0.1, -0.4, 0.5))


def test_bootstrap_interval_contains_the_mean_and_is_reproducible():
    diffs = [0.0] * 30 + [-1.0] * 6 + [1.0] * 2
    a = stats.paired_bootstrap(diffs, 500, 7)
    assert a == stats.paired_bootstrap(diffs, 500, 7)
    assert a[1] <= a[0] <= a[2]
    with pytest.raises(ValueError):
        stats.paired_bootstrap([])


# ------------------------------------------------------------ paired_sample_size

def test_sample_size_known_values():
    # (1.96 * sqrt(0.10) + 0.8416 * sqrt(0.0975))**2 / 0.05**2 = 311.6, rounded up
    assert stats.paired_sample_size(0.10, 0.05) == 312
    assert stats.paired_sample_size(0.20, 0.10) == 155


def test_sample_size_grows_as_the_difference_shrinks():
    assert stats.paired_sample_size(0.05, 0.02) > stats.paired_sample_size(0.05, 0.04)


@pytest.mark.parametrize("psi, delta", [(0.05, 0.0), (0.01, 0.2), (0.045, 0.05), (0.10, 0.10)])
def test_sample_size_rejects_impossible_inputs(psi, delta):
    # A paired difference cannot exceed the disagreement rate; at delta == psi it is degenerate.
    with pytest.raises(ValueError):
        stats.paired_sample_size(psi, delta)


def test_wilson_is_lab_2_1s():
    lo, hi = stats.wilson_interval(8, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.4902, 0.9433)


# ------------------------------------------------------------ cluster_bootstrap

def test_cluster_bootstrap_point_estimate_weights_tickets_not_clusters():
    # Three tickets in two families: the mean is over tickets, 2/3, not over families, 1/2.
    mean, lo, hi = stats.cluster_bootstrap([[1.0, 1.0], [0.0]], n_resamples=50)
    assert mean == pytest.approx(2 / 3) and 0.0 <= lo <= hi <= 1.0


def test_cluster_bootstrap_of_a_constant_is_that_constant():
    assert stats.cluster_bootstrap([[0.5, 0.5], [0.5]], 50) == pytest.approx((0.5, 0.5, 0.5))


def test_cluster_bootstrap_follows_the_docstring_exactly():
    clusters = [[0.0, -1.0], [1.0], [0.0, 0.0, 0.5], [-1.0]]
    # Locked so every implementation agrees: 4 clusters, 10 resamples, seed 3.
    assert stats.cluster_bootstrap(clusters, 10, 3) == pytest.approx((-1 / 14, -1.0, 0.25))


def test_cluster_bootstrap_is_wider_than_ticket_bootstrap_when_families_move_together():
    clusters = [[-1.0] * 5] * 3 + [[0.0] * 5] * 17
    flat = [x for c in clusters for x in c]
    _, cl, ch = stats.cluster_bootstrap(clusters, 1000, 7)
    _, tl, th = stats.paired_bootstrap(flat, 1000, 7)
    assert ch - cl > th - tl
    with pytest.raises(ValueError):
        stats.cluster_bootstrap([])
