"""TODO 1 (one minute's verdict), TODO 2 (the rollout) and TODO 3 (the AI feature's kill switch), on small
hand-checkable inputs. Policy and SLO targets are Relay 4.29.0's own (vendor/config/)."""

import pytest

from canary import policy, slos
from canary.analysis import bad_share, burn, minute_verdict
from canary.killswitch import feature_verdict, watch, z_two_proportion
from canary.rollout import run_canary
from canary.traffic import Counts, minute_counts

P, S = policy(), slos()


# --- provided -----------------------------------------------------------------------------------------------

def test_the_draws_are_deterministic_and_split_by_share():
    scn = {"id": "x", "rate_per_minute": 1000, "stable": {"error_p": 0.01, "slow_p": 0.0},
           "canary": {"error_p": 0.5, "slow_p": 0.0}}
    s, c = minute_counts(scn, 3, 0.05)
    assert (s.requests, c.requests) == (950, 50) and minute_counts(scn, 3, 0.05) == (s, c)
    assert 10 < c.errors < 40


def test_burn_follows_chapter_16():
    # 1.44% errors against a 99.9% target is a burn rate of 14.4
    assert burn(Counts(10000, 144, 0), "SLO-API-AVAIL", 0.999) == pytest.approx(14.4)
    assert bad_share(Counts(100, 20, 8), "SLO-API-LATENCY") == pytest.approx(0.1)  # 8 slow of 80 below 500
    assert bad_share(Counts(0, 0, 0), "SLO-API-AVAIL") is None


# --- TODO 1 -------------------------------------------------------------------------------------------------

STABLE = Counts(1140, 0, 4)


@pytest.mark.parametrize("canary, window, expected", [
    (Counts(60, 2, 0), Counts(99, 2, 0), "too-few"),
    (Counts(60, 2, 0), Counts(300, 2, 0), "bad:SLO-API-AVAIL"),        # 3.3% errors: burn 33
    (Counts(60, 0, 1), Counts(300, 0, 1), "ok"),                       # 1 slow of 60: 1.7%, burn 1.7
    (Counts(60, 0, 15), Counts(300, 0, 15), "bad:SLO-API-LATENCY"),    # 25% slow: burn 25
    (Counts(60, 1, 0), Counts(300, 1, 0), "bad:SLO-API-AVAIL"),        # 1 of 60 is 1.67%: burn 16.7
])
def test_minute_verdicts(canary, window, expected):
    assert minute_verdict(STABLE, canary, window, P, S) == expected


def test_both_versions_burning_is_not_the_release():
    stable = Counts(1140, 40, 0)  # 3.5%
    assert minute_verdict(stable, Counts(60, 2, 0), Counts(300, 2, 0), P, S) == "both:SLO-API-AVAIL"


def test_a_canary_much_worse_during_a_shared_problem_is_bad_not_both():
    stable = Counts(1140, 23, 0)  # 2.0%
    assert minute_verdict(stable, Counts(60, 18, 0), Counts(300, 18, 0), P, S) == "bad:SLO-API-AVAIL"  # 30%
    assert minute_verdict(stable, Counts(60, 2, 0), Counts(300, 2, 0), P, S) == "both:SLO-API-AVAIL"   # 3.3%


def test_a_minute_when_only_stable_burns_is_a_hold():
    assert minute_verdict(Counts(1140, 40, 0), Counts(60, 0, 0), Counts(300, 0, 0), P, S) == "stable:SLO-API-AVAIL"


def test_a_canary_no_worse_than_stable_is_not_bad():
    stable = Counts(1000, 14, 0)  # 1.4%: burn 14, just under the threshold
    assert minute_verdict(stable, Counts(100, 1, 0), Counts(300, 1, 0), P, S) == "ok"  # 1.0% is better


# --- TODO 2 -------------------------------------------------------------------------------------------------

def scn(**over):
    base = {"id": "t", "rate_per_minute": 1200, "max_minutes": 180, "stable": {"error_p": 0.0, "slow_p": 0.0},
            "canary": {"error_p": 0.0, "slow_p": 0.0}}
    base.update(over)
    return base


def test_a_clean_release_walks_every_step():
    r = run_canary(scn(), P, S)
    assert (r.decision, r.minute, r.percent) == ("promoted", 45, 100)
    assert [e for _, e in r.events] == ["step 5%", "step 25%", "step 50%", "promoted to 100%"]
    assert [m for m, _ in r.events] == [0, 16, 31, 45]  # minute 0 cannot be judged: 60 requests in the window


def test_a_failing_canary_is_rolled_back_after_three_bad_minutes_in_a_row():
    r = run_canary(scn(canary={"error_p": 1.0, "slow_p": 0.0}), P, S)
    assert (r.decision, r.minute, r.percent) == ("rolled back", 3, 5)
    assert r.canary.requests == 240 and r.bad_served == 240


def test_a_single_bad_minute_does_not_roll_back():
    r = run_canary(scn(incident={"from": 5, "to": 5, "versions": ["canary"], "error_p": 1.0}), P, S)
    assert r.decision == "promoted" and r.minute == 46


def test_a_shared_problem_holds_and_pages_once():
    r = run_canary(scn(incident={"from": 3, "to": 12, "versions": ["stable", "canary"], "error_p": 1.0}), P, S)
    assert r.decision == "promoted" and r.pages == [3] and r.minute == 45 + 10


def test_a_canary_that_cannot_be_judged_is_never_promoted():
    r = run_canary(scn(rate_per_minute=30), P, S)
    assert (r.decision, r.minute) == ("rolled back: not judged", 59)


# --- TODO 3 -------------------------------------------------------------------------------------------------

def test_z_by_hand():
    # 30 of 100 against 15 of 100: pooled 0.225; z = 0.15 / sqrt(0.225 * 0.775 * 0.02) = 2.5400
    assert z_two_proportion(30, 100, 15, 100) == pytest.approx(2.5400, abs=1e-4)
    assert z_two_proportion(0, 10, 0, 10) == 0.0


RULE = P["ai_feature_rule"]


@pytest.mark.parametrize("cohort, control, trip", [
    ((30, 100), (15, 100), True),
    ((30, 100), (15, 19), False),       # too few in the control
    ((19, 100), (15, 100), False),      # 4 points: under the 5-point minimum
    ((22, 100), (15, 100), False),      # 7 points but z = 1.27
])
def test_feature_verdicts(cohort, control, trip):
    assert feature_verdict(cohort, control, RULE)[0] is trip


def test_the_switch_trips_once_and_later_tickets_get_the_stable_route():
    a = {"id": "k", "feature": "f", "rollout_percent": 50, "workspaces": 50, "tickets_per_hour": 240, "hours": 4,
         "bad_p": {"feature": 0.9, "control": 0.1}, "confirm_mean_minutes": 1, "check_every_minutes": 5}
    w = watch(a, RULE)
    assert w.tripped_at is not None and w.tripped_at % 5 == 0
    assert [(r["action"], r["actor"], r["outcome"]) for r in w.log] == [("trip", "automation:canary-ai-quality",
                                                                           "done")]
    assert w.first_after_trip is not None and w.first_after_trip >= w.tripped_at
    assert 0 < w.extra_bad <= w.bad_with_feature <= w.with_feature


def test_no_difference_rarely_trips():
    a = {"id": "n", "feature": "f", "rollout_percent": 50, "workspaces": 50, "tickets_per_hour": 240, "hours": 2,
         "bad_p": {"feature": 0.1, "control": 0.1}, "confirm_mean_minutes": 1, "check_every_minutes": 60}
    assert watch(a, RULE).tripped_at is None


def test_review_probe_pa_a_shared_problem_that_never_clears_is_rolled_back_after_the_hold_limit():
    r = run_canary(scn(max_minutes=600, incident={"from": 2, "to": 999, "versions": ["stable", "canary"],
                                                  "error_p": 0.03}), P, S)
    assert r.decision == "rolled back: shared problem did not clear" and r.percent == 5
    assert r.minute < 2 + P["max_hold_minutes"] + 15


def test_review_probe_pb_a_far_worse_canary_during_a_shared_problem_is_rolled_back_at_once():
    r = run_canary(scn(canary={"error_p": 0.30, "slow_p": 0.0},
                       incident={"from": 2, "to": 999, "versions": ["stable"], "error_p": 0.02}), P, S)
    assert (r.decision, r.percent) == ("rolled back", 5) and r.minute <= 5
