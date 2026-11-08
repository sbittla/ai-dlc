"""Specification tests for Lab 1.2.

The toy fixture below is a classic Simpson's paradox: the AI arm is slower on
every task size, yet looks faster when the arms are pooled, because it did
mostly small tasks. If your functions handle this fixture correctly, they
will handle the vendor's data correctly.
"""

import pytest
from conftest import DATA_DIR

from audit import analysis
from audit.analysis import Attempt


def a(i, arm, size, minutes, passed=True, defects=0):
    return Attempt(f"T{i}", "dev01", arm, size, minutes, passed, defects)


@pytest.fixture
def simpson():
    rows = []
    i = 0
    # Control: 1 small (60 min), 1 medium (180), 2 large (480 each)
    for size, minutes in [("S", 60), ("M", 180), ("L", 480), ("L", 480)]:
        i += 1
        rows.append(a(i, "control", size, minutes))
    # AI: 3 small (66 each), 1 medium (198), 1 large (528); 10% slower everywhere
    for size, minutes, passed in [("S", 66, True), ("S", 66, True), ("S", 66, False), ("M", 198, True), ("L", 528, True)]:
        i += 1
        rows.append(a(i, "ai", size, minutes, passed))
    return rows


EVEN = {"S": 1 / 3, "M": 1 / 3, "L": 1 / 3}


def test_naive_speedup_is_fooled_by_the_mix(simpson):
    # control mean = 1200/4 = 300; AI mean = 924/5 = 184.8
    assert analysis.naive_speedup(simpson) == pytest.approx(1 - 184.8 / 300)
    assert analysis.naive_speedup(simpson) > 0.3


def test_task_mix(simpson):
    assert analysis.task_mix(simpson, "control") == pytest.approx({"S": 0.25, "M": 0.25, "L": 0.5})
    assert analysis.task_mix(simpson, "ai") == pytest.approx({"S": 0.6, "M": 0.2, "L": 0.2})


def test_speedup_by_size_reveals_the_truth(simpson):
    by_size = analysis.speedup_by_size(simpson)
    for s in analysis.SIZES:
        assert by_size[s] == pytest.approx(-0.10)


def test_reweighted_speedup(simpson):
    assert analysis.reweighted_speedup(simpson, EVEN) == pytest.approx(-0.10)
    with pytest.raises(ValueError):
        analysis.reweighted_speedup(simpson, {"S": 0.5, "M": 0.5, "L": 0.5})


def test_acceptance_rate_plain_and_standardized(simpson):
    assert analysis.acceptance_rate(simpson, "ai") == pytest.approx(4 / 5)
    # standardized: S 2/3, M 1, L 1 with equal weights
    assert analysis.acceptance_rate(simpson, "ai", EVEN) == pytest.approx((2 / 3 + 1 + 1) / 3)


def test_minutes_per_accepted_task(simpson):
    minutes = (66 + 198 + 528) / 3
    acc = (2 / 3 + 1 + 1) / 3
    assert analysis.minutes_per_accepted_task(simpson, "ai", EVEN) == pytest.approx(minutes / acc)


@pytest.fixture
def noisy():
    """Two attempts per cell with different times, so resamples differ."""
    rows, i = [], 0
    for arm, factor in (("control", 1.0), ("ai", 0.9)):
        for size, base in (("S", 60), ("M", 180), ("L", 480)):
            for jitter in (0.8, 1.2):
                i += 1
                rows.append(a(i, arm, size, base * factor * jitter))
    return rows


def test_bootstrap_ci_is_deterministic_and_has_width(noisy):
    lo, hi = analysis.bootstrap_ci(noisy, EVEN, n_resamples=500, seed=1)
    assert (lo, hi) == analysis.bootstrap_ci(noisy, EVEN, n_resamples=500, seed=1)
    assert lo < hi
    assert lo <= analysis.reweighted_speedup(noisy, EVEN) <= hi


def test_bootstrap_follows_the_documented_algorithm(noisy):
    """Re-implements the docstring's algorithm independently and compares."""
    import random
    rng = random.Random(3)
    cells = [[r for r in noisy if r.arm == arm and r.task_size == s] for arm in ("control", "ai") for s in ("S", "M", "L")]
    est = sorted(analysis.reweighted_speedup([rng.choice(c) for c in cells for _ in c], EVEN) for _ in range(200))
    assert analysis.bootstrap_ci(noisy, EVEN, n_resamples=200, seed=3) == (est[5], est[194])


# ----------------------------------------------------------- vendor data

RELAY_MIX = {"S": 0.25, "M": 0.45, "L": 0.30}


@pytest.fixture(scope="module")
def result():
    return analysis.audit(analysis.load(DATA_DIR / "trial.csv"), RELAY_MIX)


def test_vendor_headline_reproduces(result):
    assert result.naive_speedup == pytest.approx(0.382, abs=0.001)


def test_selection_bias_is_visible(result):
    assert result.mix_ai["S"] > result.mix_control["S"] + 0.2
    assert result.mix_ai["L"] < result.mix_control["L"] - 0.1


def test_effect_depends_on_task_size(result):
    assert result.speedup_by_size["S"] > 0.2
    assert result.speedup_by_size["L"] < 0


def test_on_relays_mix_there_is_no_evidence_of_a_speedup(result):
    assert result.reweighted_speedup == pytest.approx(-0.072, abs=0.001)
    lo, hi = result.ci
    assert lo < 0 < hi  # the interval includes zero
    assert result.quality_adjusted_speedup < result.reweighted_speedup
    assert result.defects_ai > result.defects_control


def test_defect_comparison_reverses_when_standardized(result):
    # Raw, the AI arm looks better on defects; on Relay's mix it looks worse.
    assert result.defects_ai_raw < result.defects_control_raw
    assert result.defects_ai > result.defects_control


def test_vendor_interval_reproduces(result):
    lo, hi = result.ci
    assert lo == pytest.approx(-0.220, abs=0.001) and hi == pytest.approx(0.065, abs=0.001)
