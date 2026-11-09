"""TODO 4: compare and the gate rule, on hand-made records.

Four tasks in two families, three runs each. Reference successes by task: T1 3 of 3, T2 0 of 3, T3 3 of 3,
T4 1 of 3. Candidate: T1 3, T2 3, T3 2, T4 1. Per-task differences in points: 0, +100, -33.3, 0; mean +16.7.
By majority: the reference is right on T1 and T3, the candidate on T1, T2 and T3, so b = 0 and c = 1, p = 1.
"""

import pytest

from agentlab.compare import compare, gate
from agentlab.runtime import RunRecord

REF = {"T1": 3, "T2": 0, "T3": 3, "T4": 1}
CAND = {"T1": 3, "T2": 3, "T3": 2, "T4": 1}
FAMILY = {"T1": "F1", "T2": "F1", "T3": "F2", "T4": "F2"}


def rec(task, design, run, success, usd):
    return RunRecord(task_id=task, family=FAMILY[task], shape="local", difficulty="easy", design=design, run=run,
                     status="finished", reason="", pr_opened=True, variant="correct", success=success,
                     wrong_pr=False, usd=usd, seconds=1.0, model_calls=1, tool_calls=1, steps=2, refusals={},
                     redundant_reads=0, approvals=1, trail_ok=True, policy_ok=True)


def records():
    out = []
    for task in REF:
        for run in (1, 2, 3):
            out.append(rec(task, "ref", run, run <= REF[task], 0.20))
            out.append(rec(task, "cand", run, run <= CAND[task], 0.15))
    return out


def test_difference_counts_and_cost_by_hand():
    c = compare(records(), "cand", "ref")
    assert c.diff == pytest.approx(100 / 6)
    assert (c.b, c.c, c.p) == (0, 1, 1.0)
    assert c.cost_change == pytest.approx(-0.25)
    assert c.low <= c.diff <= c.high


def test_the_interval_resamples_families():
    c = compare(records(), "cand", "ref")
    # Family means are +50 (F1) and -16.7 (F2): every resample is one of three family mixes.
    assert c.low == pytest.approx(-100 / 6) and c.high == pytest.approx(50.0)


@pytest.mark.parametrize("low, high, cost, verdict", [
    (-6.0, 2.0, -0.5, "FAIL: a loss larger than the margin cannot be ruled out"),
    (-4.0, 2.0, -0.10, "PASS: non-inferior within the margin, and cheaper"),
    (-4.0, -1.0, 0.0, "FAIL: worse beyond noise"),
    (1.0, 4.0, 0.2, "PASS: improvement"),
    (-1.0, 4.0, 0.2, "PASS: no clear change"),
])
def test_gate_rule(low, high, cost, verdict):
    from agentlab.compare import Comparison
    c = Comparison("c", "r", "success", (low + high) / 2, low, high, 0, 0, 1.0, cost)
    assert gate(c, {"margin_points": 5, "benefit_cost_reduction": 0.10}) == verdict
