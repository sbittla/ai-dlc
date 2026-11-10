"""relay.routing.costs (4.28.0, ADR-042): one price table, cost per call, cost per success, the spend monitor."""

import math

import pytest

from relay.agents.budget import DEFAULT_PRICES, PRICES_AS_OF as AGENT_PRICES_AS_OF
from relay.routing import CACHE_WRITE_MULTIPLIER, PRICES, PRICES_AS_OF, Alert, SpendMonitor, call_cost, cost_per_success


def test_the_price_table_is_chapter_10s_table():
    assert PRICES_AS_OF == AGENT_PRICES_AS_OF == "2027-01-12"
    for model, price in DEFAULT_PRICES.items():
        ours = PRICES[model]
        assert (ours.input_per_mtok, ours.output_per_mtok, ours.cache_read_per_mtok) == (
            price.input_per_mtok, price.output_per_mtok, price.cache_read_per_mtok)


def test_cache_reads_are_5_percent_and_writes_carry_the_assumed_surcharge():
    large = PRICES["sim-large"]
    assert large.cache_read_per_mtok == pytest.approx(0.05 * large.input_per_mtok)
    assert CACHE_WRITE_MULTIPLIER == 1.25 and large.cache_write_per_mtok == 5.0


def test_a_call_costs_its_parts():
    large = PRICES["sim-large"]
    # 1,000 input tokens (600 read from cache, 200 written to it, 200 plain) and 300 output tokens, by hand:
    # 200 x 4 + 600 x 0.20 + 200 x 5 + 300 x 20 = 800 + 120 + 1,000 + 6,000 = 7,920 per million = $0.00792
    assert call_cost(large, 1000, 300, cache_read_tokens=600, cache_write_tokens=200) == pytest.approx(0.00792)
    with pytest.raises(ValueError):
        call_cost(large, 100, 10, cache_read_tokens=80, cache_write_tokens=40)


def test_cost_per_success_counts_every_call_but_only_good_outcomes():
    assert cost_per_success([0.01, 0.01, 0.01, 0.01], 2) == pytest.approx(0.02)
    assert math.isinf(cost_per_success([0.01], 0))


def test_the_monitor_alerts_when_cost_per_success_rises_past_the_tolerance():
    monitor = SpendMonitor(baseline_per_success=0.002, tolerance=0.25, window_days=2, min_successes=10)
    days = [("d1", 0.20, 100), ("d2", 0.22, 100), ("d3", 0.60, 100), ("d4", 0.60, 100)]
    assert monitor.check(days) == [Alert("d3", "cost_per_success", 0.0041, 0.0025),
                                   Alert("d4", "cost_per_success", 0.006, 0.0025)]


def test_the_monitor_ignores_thin_windows_and_checks_a_daily_ceiling():
    monitor = SpendMonitor(baseline_per_success=0.002, min_successes=50, daily_ceiling_usd=1.0)
    assert monitor.check([("d1", 0.5, 10)]) == []
    assert monitor.check([("d1", 2.0, 2000)]) == [Alert("d1", "daily_spend", 2.0, 1.0)]
