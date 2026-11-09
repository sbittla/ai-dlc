"""Locks the arithmetic in book/answers/ch10-answers.md, Exercises 5 and 6 (Relay's meter, Lab 10.1's compare)."""

import pytest

from agentlab.compare import compare
from agentlab.runtime import RunRecord
from relay.agents import Budget, BudgetExceeded, Meter


def run_exercise_5(caching: bool):
    m = Meter(Budget(max_steps=40, max_usd=2.00, max_seconds=10**6))
    calls = 0
    while True:
        k = calls + 1
        tokens, cached = 50_000 * k, (50_000 * (k - 1) if caching else 0)
        try:
            m.admit(m.estimate("sim-large", tokens, 2048, cached))
        except BudgetExceeded as exc:
            return calls, m.usd, exc.kind, m.steps
        m.charge_model("agent", "sim-large", tokens, 500, 1.0, cached)
        m.charge_tool("agent", 1.0)
        calls += 1


def test_exercise_5a_without_caching():
    calls, usd, kind, steps = run_exercise_5(False)
    assert (calls, kind, steps) == (3, "usd", 6) and usd == pytest.approx(1.23)


def test_exercise_5b_with_caching():
    calls, usd, kind, steps = run_exercise_5(True)
    assert (calls, kind, steps) == (8, "usd", 16) and usd == pytest.approx(1.96)


SHARES = {"T1": (3, 3), "T2": (0, 2), "T3": (2, 1), "T4": (3, 3), "T5": (1, 3), "T6": (0, 0)}
FAMILY = {"T1": "A", "T2": "A", "T3": "B", "T4": "B", "T5": "C", "T6": "C"}


def rec(task, design, run, success):
    return RunRecord(task_id=task, family=FAMILY[task], shape="local", difficulty="easy", design=design, run=run,
                     status="finished", reason="", pr_opened=True, variant="correct", success=success,
                     wrong_pr=False, usd=0.1, seconds=1.0, model_calls=1, tool_calls=1, steps=2, refusals={},
                     redundant_reads=0, approvals=1, trail_ok=True, policy_ok=True)


def test_exercise_6():
    records = [rec(t, d, r, r <= s[i]) for t, s in SHARES.items() for i, d in enumerate(("ref", "cand"))
               for r in (1, 2, 3)]
    c = compare(records, "cand", "ref")
    assert c.diff == pytest.approx(100 / 6)
    assert (c.b, c.c, c.p) == (1, 2, 1.0)
    # family means: A (0 + 66.7) / 2, B (-33.3 + 0) / 2, C (66.7 + 0) / 2
    assert c.low == pytest.approx(-50 / 3) and c.high == pytest.approx(100 / 3)
