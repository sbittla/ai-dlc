"""Budgets and the meter (4.24.0, ADR-024). Costs are worked by hand from the assumed price table."""

import pytest

from relay.agents import DEFAULT_PRICES, PRICES_AS_OF, Budget, BudgetExceeded, Meter, Price, cost_usd


def test_cost_of_one_call_by_hand():
    # 100,000 input tokens at $4 per million is $0.40; 2,000 output at $20 per million is $0.04.
    assert cost_usd(Price(4.00, 20.00, 0.40), 100_000, 2_000) == pytest.approx(0.44)


def test_cached_input_is_charged_at_the_cache_price():
    # 90,000 of the 100,000 input tokens come from the cache: 10,000 x $4 + 90,000 x $0.20, per million.
    assert cost_usd(Price(4.00, 20.00, 0.20), 100_000, 0, cached_tokens=90_000) == pytest.approx(0.058)


def test_cached_tokens_must_be_part_of_the_input():
    with pytest.raises(ValueError):
        cost_usd(Price(4.0, 20.0, 0.4), 10, 0, cached_tokens=11)


def test_the_price_table_is_dated_and_simulated_models_carry_live_prices():
    assert PRICES_AS_OF == "2027-01-12"
    assert DEFAULT_PRICES["sim-large"] == DEFAULT_PRICES["claude-opus-5-5"] == Price(4.00, 20.00, 0.20)


def test_budget_limits_must_be_positive():
    for bad in (dict(max_steps=0, max_usd=1, max_seconds=1), dict(max_steps=1, max_usd=0, max_seconds=1),
                dict(max_steps=1, max_usd=1, max_seconds=0), dict(max_steps=1, max_usd=1, max_seconds=1,
                                                                  max_model_calls=0)):
        with pytest.raises(ValueError):
            Budget(**bad)


def test_check_refuses_once_a_limit_is_reached_not_only_when_passed():
    m = Meter(Budget(max_steps=2, max_usd=10, max_seconds=100))
    m.charge_tool("a", 1.0)
    m.check()
    m.charge_tool("a", 1.0)
    with pytest.raises(BudgetExceeded) as exc:
        m.check()
    assert (exc.value.kind, exc.value.used, exc.value.limit) == ("steps", 2, 2)


def test_check_reports_limits_in_a_fixed_order():
    m = Meter(Budget(max_steps=1, max_usd=0.01, max_seconds=1, max_model_calls=1))
    m.charge_model("a", "sim-large", 100_000, 0, 5.0)  # every limit reached at once
    with pytest.raises(BudgetExceeded) as exc:
        m.check()
    assert exc.value.kind == "steps"


def test_admit_refuses_a_call_that_would_cross_the_money_limit():
    m = Meter(Budget(max_steps=100, max_usd=1.00, max_seconds=1000))
    m.charge_model("a", "sim-large", 200_000, 0, 1.0)  # $0.80
    m.admit(0.19)
    with pytest.raises(BudgetExceeded) as exc:
        m.admit(0.21)
    assert exc.value.kind == "usd" and exc.value.used == pytest.approx(1.01)


def test_estimate_assumes_the_whole_output_budget():
    m = Meter(Budget(max_steps=10, max_usd=1, max_seconds=10))
    assert m.estimate("sim-large", 10_000, 4_096) == pytest.approx(0.04 + 0.08192)


def test_the_meter_attributes_spend_to_each_actor_and_survives_a_checkpoint():
    m = Meter(Budget(max_steps=10, max_usd=10, max_seconds=100))
    m.charge_model("coder", "sim-large", 50_000, 1_000, 3.0)
    m.charge_model("reviewer", "sim-large", 25_000, 500, 2.0)
    m.charge_tool("coder", 8.0)
    assert m.by_actor == pytest.approx({"coder": 0.22, "reviewer": 0.11})
    assert (m.steps, m.model_calls, m.seconds) == (3, 2, 13.0)
    resumed = Meter(m.budget)
    resumed.restore(m.snapshot())
    assert resumed.snapshot() == m.snapshot()
