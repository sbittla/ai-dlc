"""The regression gate on small, hand-checkable fixtures."""

import pytest

from evalsuite import gate
from evalsuite.dataset import Leakage, Pin
from evalsuite.runner import Record

POLICY = {
    "policy": "test", "repeats": 3, "bootstrap": {"resamples": 400, "seed": 7},
    "min_schema_valid": 0.9, "min_accuracy": 0.5, "regression_margin_points": 5.0,
    "max_injection_rate": 0.05, "cost_warn_increase": 0.25, "slices": ["language:de"],
    "slice_warn_drop_points": 5.0, "slice_max_p": 0.05, "benefit_cost_reduction": 0.10,
}
PIN = Pin(True, "pinned")
CLEAN = Leakage([], [], [])


def tickets(n=40, de=8):
    return [{"id": f"T{i:03d}", "family": f"T{i:03d}", "kind": "plain", "language": "de" if i < de else "en",
             "source": "curated", "difficulty": "easy"} for i in range(n)]


def records(ts, wrong=(), name="c", error=None, injected=(), obeyed=(), cost=0.001):
    """Three runs per ticket; tickets in `wrong` are wrong on every run."""
    out = []
    for t in ts:
        for run in (1, 2, 3):
            ok = t["id"] not in wrong
            out.append(Record(name, t["id"], run, error if ok is False and error else None, name,
                              {} if ok else None, ok, t["id"] in injected, t["id"] in obeyed and run == 1, cost))
    return out


def status(result, name):
    return next(r.status for r in result.rules if r.name == name)


def test_identical_candidate_passes_every_rule():
    ts = tickets()
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts))
    assert g.decision == "pass"
    assert [r.name for r in g.rules] == ["dataset", "leakage", "complete", "schema", "floor", "regression",
                                         "injection", "cost", "slice language:de"]
    assert {r.status for r in g.rules} == {"pass"}
    assert (g.overall.diff, g.overall.worse, g.overall.better) == (0.0, 0, 0)


def test_a_clear_regression_fails_as_worse_beyond_noise():
    ts = tickets()
    wrong = {f"T{i:03d}" for i in range(10, 22)}         # 12 of 40 tickets newly wrong
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts, wrong))
    assert g.decision == "fail"
    rule = next(r for r in g.rules if r.name == "regression")
    assert rule.status == "fail" and "worse beyond noise" in rule.detail
    assert (g.overall.worse, g.overall.better) == (12, 0)
    assert g.overall.diff == pytest.approx(-0.3)


def test_a_small_set_cannot_rule_out_a_large_drop():
    ts = tickets(n=20, de=0)
    g = gate.evaluate_gate({**POLICY, "slices": []}, PIN, CLEAN, ts, records(ts, name="b"), records(ts, {"T005"}))
    rule = next(r for r in g.rules if r.name == "regression")
    assert rule.status == "fail" and "cannot rule out" in rule.detail   # one ticket in 20 is 5 points
    assert g.overall.high == 0.0


def test_unpinned_data_and_leaked_prompts_fail_closed():
    ts = tickets()
    base, cand = records(ts, name="b"), records(ts)
    g = gate.evaluate_gate(POLICY, Pin(False, "hash mismatch"), Leakage([], [("T003", 1.0)], []), ts, base, cand)
    assert status(g, "dataset") == "fail" and status(g, "leakage") == "fail" and g.decision == "fail"


def test_a_budget_stop_makes_the_run_incomplete():
    ts = tickets()
    cand = records(ts, {"T030"}, error="budget")
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), cand)
    assert status(g, "complete") == "fail"


def test_injection_rate_is_an_absolute_limit():
    ts = tickets()
    inj = {"T030", "T031"}                                 # 6 injected calls; obeyed on run 1 of each
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b", injected=inj),
                           records(ts, injected=inj, obeyed=inj))
    assert status(g, "injection") == "fail"               # 2 of 6 = 33% > 5%


def test_a_slice_drop_inside_the_noise_warns_without_failing():
    ts = tickets(n=200)                                   # large enough overall to clear the margin
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts, {"T000"}))
    assert status(g, "slice language:de") == "warn"       # 1 of 8 German tickets: -12.5 points
    assert status(g, "regression") == "pass" and g.decision == "pass"


def test_a_slice_fails_only_when_interval_and_mcnemar_agree():
    ts = tickets()
    four = {f"T{i:03d}" for i in range(4)}                # 4 of 8 worse: McNemar p = 2/16 = 0.125
    six = {f"T{i:03d}" for i in range(6)}                 # 6 of 8 worse: McNemar p = 2/64 = 0.031
    g4 = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts, four))
    g6 = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts, six))
    assert status(g4, "slice language:de") == "warn"
    assert status(g6, "slice language:de") == "fail"


def test_cost_increase_warns():
    ts = tickets()
    g = gate.evaluate_gate(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts, cost=0.002))
    assert status(g, "cost") == "warn" and g.decision == "pass"


def test_points_never_prints_negative_zero():
    assert gate.points(-0.00001) == "+0.0"
    assert gate.points(-0.0417) == "-4.2"


def test_unknown_rule_is_an_error():
    ts = tickets()
    f = gate.gather(POLICY, PIN, CLEAN, ts, records(ts, name="b"), records(ts))
    with pytest.raises(KeyError):
        gate.rule_status("speed", f, POLICY)


def test_a_cheaper_candidate_is_judged_by_the_margin_alone():
    ts = tickets(n=400, de=0)
    wrong = {f"T{i:03d}" for i in range(100, 108)}        # 8 of 400 newly wrong: -2 points, consistently
    base = records(ts, name="b", cost=0.001)
    policy = {**POLICY, "slices": []}
    same_price = gate.evaluate_gate(policy, PIN, CLEAN, ts, base, records(ts, wrong, cost=0.001))
    cheaper = gate.evaluate_gate(policy, PIN, CLEAN, ts, base, records(ts, wrong, cost=0.0005))
    assert same_price.overall.high < 0 and same_price.overall.low > -0.05
    assert status(same_price, "regression") == "fail"     # worse beyond noise, and nothing bought
    assert status(cheaper, "regression") == "pass"        # within the margin, for half the cost
