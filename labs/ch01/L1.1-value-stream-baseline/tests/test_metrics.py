"""Specification tests for Lab 1.1.

Two kinds of tests:

1. Hand-computed fixtures: tiny datasets where you can check every number on
   paper. These are the real specification of each metric.
2. Dataset checks: the full Relay dataset, with values fixed by the
   reference solution. If your fixture tests pass but these fail, re-read the
   docstring definitions: the difference is almost always a definition choice
   (for example, including hotfixes or reverted changes).
"""

from datetime import datetime, timedelta

import pytest
from conftest import DATA_DIR

from vsm import data, metrics
from vsm.data import Change, Deployment, MonthlyCost

T0 = datetime(2026, 1, 5, 9, 0)


def change(cid, *, kind="feature", coding=10, review_wait=5, review=2, merge_wait=1, deploy_wait=6,
           reverted=False, ai=False, lines=100, deploy_id="D1"):
    first = T0
    opened = first + timedelta(hours=coding)
    first_review = opened + timedelta(hours=review_wait)
    approved = first_review + timedelta(hours=review)
    merged = approved + timedelta(hours=merge_wait)
    deployed = merged + timedelta(hours=deploy_wait)
    return Change(cid, kind, first, opened, first_review, approved, merged, deployed, deploy_id, lines, ai, reverted)


def deployment(did, *, kind="planned", failed=False, recovery_h=None, at=T0):
    restored = at + timedelta(hours=recovery_h) if recovery_h is not None else None
    return Deployment(did, at, kind, failed, restored)


# ---------------------------------------------------------------- fixtures

def test_percentile_nearest_rank():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert metrics.percentile(values, 90) == 9
    assert metrics.percentile(values, 50) == 5
    assert metrics.percentile([42], 90) == 42


def test_change_lead_time_median_and_p90():
    # Total hours per change = coding + 5 + 2 + 1 + 6 = coding + 14
    changes = [change(f"C{i}", coding=c) for i, c in enumerate([6, 16, 26, 36, 86])]
    lt = metrics.change_lead_time(changes)
    assert lt.n == 5
    assert lt.median_h == pytest.approx(40.0)  # 26 + 14
    assert lt.p90_h == pytest.approx(100.0)    # nearest rank: ceil(0.9*5)=5th value = 86 + 14


def test_lead_time_includes_hotfixes_and_reverted_changes():
    changes = [change("A", coding=6), change("B", kind="hotfix", coding=1), change("C", reverted=True, coding=46)]
    assert metrics.change_lead_time(changes).n == 3


def test_deployment_frequency():
    deps = [deployment(f"D{i}") for i in range(6)] + [deployment("H1", kind="hotfix")]
    assert metrics.deployment_frequency_per_week(deps, weeks=2) == pytest.approx(3.5)
    with pytest.raises(ValueError):
        metrics.deployment_frequency_per_week(deps, weeks=0)


def test_change_fail_rate_counts_all_deployment_kinds():
    deps = [deployment("D1", failed=True, recovery_h=2), deployment("D2"), deployment("D3"),
            deployment("H1", kind="hotfix")]
    assert metrics.change_fail_rate(deps) == pytest.approx(0.25)


def test_recovery_time_is_median_of_failed_only():
    deps = [deployment("D1", failed=True, recovery_h=2), deployment("D2", failed=True, recovery_h=10),
            deployment("D3", failed=True, recovery_h=4), deployment("D4")]
    assert metrics.recovery_time_hours(deps) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        metrics.recovery_time_hours([deployment("D4")])


def test_rework_rate():
    deps = [deployment("D1"), deployment("D2"), deployment("D3"), deployment("H1", kind="hotfix")]
    assert metrics.rework_rate(deps) == pytest.approx(0.25)


def test_stage_hours():
    c = change("A", coding=10, review_wait=5, review=2, merge_wait=1, deploy_wait=6)
    assert metrics.stage_hours(c) == {
        "coding": 10, "review_wait": 5, "review": 2, "merge_wait": 1, "deploy_wait": 6,
    }


def test_flow_breakdown_sums_over_changes_and_excludes_hotfixes():
    a = change("A", coding=10, review_wait=5, review=2, merge_wait=1, deploy_wait=6)   # active 12 of 24
    b = change("B", coding=2, review_wait=20, review=2, merge_wait=1, deploy_wait=23)  # active 4 of 48
    h = change("H", kind="hotfix", coding=1, review_wait=0, review=1, merge_wait=0, deploy_wait=0)
    flow = metrics.flow_breakdown([a, b, h])
    assert flow.flow_efficiency == pytest.approx(16 / 72)  # not the mean of 0.5 and 0.083
    assert flow.median_stage_h["review_wait"] == pytest.approx(12.5)


def test_cost_per_accepted_change_excludes_reverted_and_hotfixes():
    changes = [change("A"), change("B"), change("C", reverted=True), change("H", kind="hotfix")]
    costs = [MonthlyCost("2026-01", 1000, 100, 100)]
    assert metrics.cost_per_accepted_change(changes, costs) == pytest.approx(600.0)


# ----------------------------------------------------------- full dataset

@pytest.fixture(scope="module")
def q1():
    return metrics.baseline(data.for_period(data.load(DATA_DIR), "2026Q1"), "2026Q1")


@pytest.fixture(scope="module")
def q2():
    return metrics.baseline(data.for_period(data.load(DATA_DIR), "2026Q2"), "2026Q2")


def test_littles_law():
    # 2 changes arrive per hour and each waits 3 hours on average: 6 waiting
    assert metrics.littles_law(2.0, 3.0) == pytest.approx(6.0)


def test_next_weekday_train():
    fri_evening = datetime(2026, 1, 9, 18, 0)     # Friday 18:00
    assert metrics.next_weekday_train(fri_evening) == datetime(2026, 1, 12, 15, 0)  # Monday 15:00
    tue_morning = datetime(2026, 1, 6, 9, 0)
    assert metrics.next_weekday_train(tue_morning) == datetime(2026, 1, 6, 15, 0)
    exactly = datetime(2026, 1, 6, 15, 0)
    assert metrics.next_weekday_train(exactly) == exactly


def test_daily_deploy_counterfactual_uses_merge_time_and_skips_hotfixes():
    # T0 is Monday 09:00. Merged after coding 10 + review wait 5 + review 2 + merge wait 1 = 18 h:
    # Tuesday 03:00, so the next train is Tuesday 15:00 = 30 h after first commit.
    c = change("A")
    h = change("H", kind="hotfix")
    lt = metrics.daily_deploy_counterfactual([c, h])
    assert lt.n == 1
    assert lt.median_h == pytest.approx(30.0)


def test_dataset_q1_baseline(q1):
    assert q1.feature_changes == 96
    assert q1.deployments == 24
    assert q1.change_fail_rate == pytest.approx(3 / 24)
    assert q1.rework_rate == pytest.approx(2 / 24)
    assert q1.accepted_changes == 93
    assert q1.lead_time.median_h == pytest.approx(80.1, abs=0.1)
    assert q1.cost_per_accepted_change_usd == pytest.approx(370_200 / 93)
    assert q1.deploys_per_week == pytest.approx(24 / (90 / 7))


# Every number Chapter 1 quotes, locked to the reference solution.
GOLDEN = {
    "2026Q1": dict(feature_changes=96, deployments=24, failed=3, hotfix=2, reverted=3, per_week=1.87,
                   lt_med=80.1, lt_p90=140.0, flt_med=80.8, cfr=12.5, rec_med=5.1, rec_mean=4.6, rework=8.3,
                   coding=22.0, review_wait=5.4, review=4.1, merge_wait=2.1, deploy_wait=42.3, flow=33.0,
                   accepted=93, cost=3981, rw_mean=6.6, rw_p90=11.5, littles=0.29, load=433, lines=12577,
                   size=100.5, ai=12.5, daily=55.0),
    "2026Q2": dict(feature_changes=192, deployments=27, failed=5, hotfix=6, reverted=12, per_week=2.08,
                   lt_med=87.7, lt_p90=142.4, flt_med=89.8, cfr=18.5, rec_med=3.2, rec_mean=5.3, rework=22.2,
                   coding=7.9, review_wait=16.9, review=5.0, merge_wait=2.0, deploy_wait=45.9, flow=16.9,
                   accepted=180, cost=2172, rw_mean=20.1, rw_p90=36.8, littles=1.77, load=1046, lines=63833,
                   size=258, ai=85.4, daily=55.4),
}


@pytest.mark.parametrize("period", sorted(GOLDEN))
def test_golden_numbers_quoted_in_chapter_1(period):
    b = metrics.baseline(data.for_period(data.load(DATA_DIR), period), period)
    g = GOLDEN[period]
    near = lambda x: pytest.approx(x, abs=0.051)
    assert (b.feature_changes, b.deployments, b.failed_deployments, b.hotfix_deployments, b.reverted_changes) ==         (g["feature_changes"], g["deployments"], g["failed"], g["hotfix"], g["reverted"])
    assert round(b.deploys_per_week, 2) == g["per_week"]
    assert b.lead_time.median_h == near(g["lt_med"]) and b.lead_time.p90_h == near(g["lt_p90"])
    assert b.feature_lead_time.median_h == near(g["flt_med"])
    assert b.change_fail_rate * 100 == near(g["cfr"]) and b.rework_rate * 100 == near(g["rework"])
    assert b.recovery_time_h == near(g["rec_med"]) and b.recovery_time_mean_h == near(g["rec_mean"])
    for stage in ("coding", "review_wait", "review", "merge_wait", "deploy_wait"):
        assert b.flow.median_stage_h[stage] == near(g[stage])
    assert b.flow.flow_efficiency * 100 == near(g["flow"])
    assert b.accepted_changes == g["accepted"] and round(b.cost_per_accepted_change_usd) == g["cost"]
    assert b.queue.mean_review_wait_h == near(g["rw_mean"]) and b.queue.p90_review_wait_h == near(g["rw_p90"])
    assert round(b.queue.avg_waiting, 2) == g["littles"]
    assert round(b.review_load_h) == g["load"] and b.lines_changed == g["lines"]
    assert b.median_change_lines == near(g["size"]) and b.ai_assisted_share * 100 == near(g["ai"])
    assert b.daily_deploy_lead_time.median_h == near(g["daily"])


def test_monthly_windows_show_false_alarms():
    months = {m.month: m for m in metrics.monthly_stability(data.load(DATA_DIR).deployments)}
    # February, before agents, breaches a 15% change-fail-rate guardrail on its own.
    assert months["2026-02"].change_fail_rate == pytest.approx(0.20)
    assert months["2026-04"].change_fail_rate == pytest.approx(2 / 7)


def test_dataset_q2_shows_the_chapter_1_pattern(q1, q2):
    # Agents made coding faster...
    assert q2.flow.median_stage_h["coding"] < q1.flow.median_stage_h["coding"] / 2
    # ...but the review queue grew, so end-to-end lead time did not improve.
    assert q2.flow.median_stage_h["review_wait"] > 2 * q1.flow.median_stage_h["review_wait"]
    assert q2.lead_time.median_h > q1.lead_time.median_h
    # Stability got worse.
    assert q2.change_fail_rate > q1.change_fail_rate
    assert q2.rework_rate > q1.rework_rate
    # And yet the naive cost metric looks better. This is the trap.
    assert q2.cost_per_accepted_change_usd < q1.cost_per_accepted_change_usd


def test_rolling_quarter_window_is_quiet_before_agents_and_fires_after():
    windows = {w.month: w for w in metrics.rolling_stability(data.load(DATA_DIR).deployments)}
    assert windows["2026-01..2026-03"].change_fail_rate == pytest.approx(3 / 24)   # below a 15% guardrail
    assert windows["2026-02..2026-04"].change_fail_rate == pytest.approx(5 / 25)   # first window above it
    assert windows["2026-04..2026-06"].rework_rate == pytest.approx(6 / 27)
