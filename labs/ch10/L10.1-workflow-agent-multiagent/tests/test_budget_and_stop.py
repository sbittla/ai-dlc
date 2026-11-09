"""TODO 1 and 2: Meter.check, Meter.admit and stop_reason, on cases small enough to work out by hand."""

import pytest

from relay.agents import Budget, BudgetExceeded, Meter, StepRecord, StopRules, stop_reason


def meter(**kw):
    return Meter(Budget(**{"max_steps": 10, "max_usd": 1.0, "max_seconds": 100, **kw}))


def test_check_passes_below_every_limit():
    m = meter()
    m.charge_tool("a", 99.0)
    m.check()


@pytest.mark.parametrize("kind, charge", [
    ("steps", lambda m: [m.charge_tool("a", 0) for _ in range(10)]),
    ("seconds", lambda m: m.charge_tool("a", 100.0)),
    ("usd", lambda m: m.charge_model("a", "sim-large", 250_000, 0, 1.0)),  # 250,000 x $4 per million = $1.00
])
def test_check_refuses_at_each_limit(kind, charge):
    m = meter()
    charge(m)
    with pytest.raises(BudgetExceeded) as exc:
        m.check()
    assert exc.value.kind == kind


def test_model_calls_limit_is_optional():
    m = meter(max_model_calls=1)
    m.charge_model("a", "sim-large", 1000, 0, 0.1)
    with pytest.raises(BudgetExceeded) as exc:
        m.check()
    assert exc.value.kind == "model_calls"


def test_admit_refuses_a_call_that_would_cross_the_money_limit():
    m = meter()
    m.charge_model("a", "sim-large", 200_000, 0, 1.0)  # $0.80
    m.admit(0.20)                                      # exactly $1.00: allowed
    with pytest.raises(BudgetExceeded) as exc:
        m.admit(0.21)
    assert exc.value.kind == "usd"


def test_admit_checks_the_other_limits_first():
    m = meter(max_steps=1)
    m.charge_tool("a", 0)
    with pytest.raises(BudgetExceeded) as exc:
        m.admit(0.0)
    assert exc.value.kind == "steps"


def test_stop_reason_none_for_a_fresh_run():
    assert stop_reason(meter(), [], StopRules()) is None


def test_stop_reason_budget_first():
    m = meter(max_steps=1)
    m.charge_tool("a", 0)
    assert stop_reason(m, [StepRecord("t", False, "x")] * 3, StopRules()) == "budget:steps"


def test_stop_reason_repeated_failure_after_three():
    h = [StepRecord("run_tests", True, "tests:a", f"red:{i}") for i in range(3)]
    assert stop_reason(meter(), h[:2], StopRules()) is None
    assert stop_reason(meter(), h, StopRules()) == "repeated_failure:tests:a"


def test_stop_reason_different_failures_do_not_add_up():
    h = [StepRecord("t", True, s, str(i)) for i, s in enumerate(["a", "b", "a", "b"])]
    assert stop_reason(meter(), h, StopRules(repeat_limit=3)) is None


def test_stop_reason_no_progress():
    h = [StepRecord("read_file", True, None, "read:a")] + [StepRecord("read_file", True, None, "read:a")] * 6
    assert stop_reason(meter(), h, StopRules(no_progress_limit=6)) == "no_progress"
    assert stop_reason(meter(), h[:6], StopRules(no_progress_limit=6)) is None  # read:a is new in the first step
