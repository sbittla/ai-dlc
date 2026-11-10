"""Numbers in book/answers/ch15-answers.md that come from Lab 15.2."""

from canary import policy, slos
from canary.killswitch import false_trips, watch
from canary.report import scenario, traffic_ids
from canary.rollout import run_canary


def test_exercise_6_hourly_checks():
    rule = policy()["ai_feature_rule"]
    w = watch(dict(scenario("ai", "A1"), check_every_minutes=60), rule)
    assert (w.tripped_at, w.with_feature, w.extra_bad, round(w.drop, 1), round(w.z, 2)) == (420, 134, 21, 9.3, 2.44)
    assert false_trips(dict(scenario("ai", "A0"), check_every_minutes=60), rule) == [8, 15]


def test_exercise_7_one_bad_minute_is_enough():
    p = dict(policy(), rollback_sustained_minutes=1)
    got = {sid: (r.decision, r.minute, r.bad_served) for sid in traffic_ids()
           for r in [run_canary(scenario("traffic", sid), p, slos())]}
    assert got == {"R1": ("promoted", 45, 61), "R2": ("rolled back", 1, 4), "R3": ("rolled back", 1, 26),
                   "R4": ("rolled back", 11, 3), "R5": ("rolled back: not judged", 59, 1),
                   "R6": ("rolled back", 7, 12)}


def test_exercise_7_the_policy_column():
    got = {sid: (r.decision, r.minute) for sid in traffic_ids()
           for r in [run_canary(scenario("traffic", sid), policy(), slos())]}
    assert got == {"R1": ("promoted", 45), "R2": ("rolled back", 3), "R3": ("rolled back", 3),
                   "R4": ("promoted", 61), "R5": ("rolled back: not judged", 59), "R6": ("promoted", 46)}


def test_why_the_slo_file_is_a_gate_path_lowering_a_target_lets_r2_through():
    """Round-2 review probe: SLO-API-AVAIL at 99% instead of 99.9%."""
    lowered = {k: dict(v) for k, v in slos().items()}
    lowered["SLO-API-AVAIL"]["target"] = 0.99
    r = run_canary(scenario("traffic", "R2"), policy(), lowered)
    assert (r.decision, r.minute, r.percent, r.bad_served) == ("promoted", 45, 100, 518)
