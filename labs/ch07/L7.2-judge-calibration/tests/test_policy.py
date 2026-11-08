"""The decision rule: when a judge may replace human labels."""

from dataclasses import replace

import pytest
from conftest import DATA_DIR

from judgecal import metrics, policy
from judgecal.calibrate import Calibration

POLICY = policy.load_policy(DATA_DIR / "judge-policy.json")

GOOD = Calibration(
    judge="j", split="heldout", items=120, confusion=metrics.Confusion(55, 3, 5, 57), kappa=0.87,
    kappa_ci=(0.77, 0.95), human_kappa=0.82,
    false_pass={"concise": 0.05, "verbose": 0.05, "own family": 0.06, "other family": 0.04},
    false_pass_n={"concise": 40, "verbose": 20, "own family": 30, "other family": 30},
    pairs=60, first_position_rate=0.5, swap_consistency=0.95, pair_accuracy=0.93,
    both_orders_decided=0.95, both_orders_accuracy=0.96,
)


def test_a_good_judge_passes_every_check():
    ok = policy.check_results(POLICY, GOOD)
    assert set(ok) == set(policy.SINGLE) | set(policy.PAIRWISE)
    assert all(ok.values())
    assert [d.allowed for d in policy.decide(POLICY, GOOD)] == [True, True]


@pytest.mark.parametrize("change, failed", [
    (dict(items=99), "items"),
    (dict(kappa_ci=(0.59, 0.95)), "kappa"),
    (dict(kappa=0.66), "human gap"),                                   # 0.82 - 0.66 = 0.16 > 0.15
    (dict(confusion=metrics.Confusion(55, 7, 5, 53)), "false pass"),   # 7 of 60 = 11.7%
    (dict(false_pass={"concise": 0.05, "verbose": 0.20, "own family": 0.06, "other family": 0.04}), "verbosity"),
    (dict(false_pass={"concise": 0.05, "verbose": 0.05, "own family": 0.17, "other family": 0.04}), "self-preference"),
    (dict(pairs=49), "pairs"),
    (dict(swap_consistency=0.89), "swap"),
    (dict(both_orders_accuracy=0.89), "accuracy"),
])
def test_each_check_fails_on_its_own(change, failed):
    ok = policy.check_results(POLICY, replace(GOOD, **change))
    assert [n for n, v in ok.items() if not v] == [failed]


def test_limits_are_inclusive():
    edge = replace(GOOD, kappa_ci=(0.60, 0.9), swap_consistency=0.90,
                   false_pass={"concise": 0.0, "verbose": 0.10, "own family": 0.10, "other family": 0.0})
    assert all(policy.check_results(POLICY, edge).values())


def test_a_failed_use_keeps_humans_for_that_use_only():
    single, pairwise = policy.decide(POLICY, replace(GOOD, swap_consistency=0.5))
    assert single.allowed and not pairwise.allowed
    assert [c.name for c in pairwise.checks] == policy.PAIRWISE
