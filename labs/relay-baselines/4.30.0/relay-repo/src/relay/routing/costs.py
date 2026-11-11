"""Prices, the cost of a call, cost per successful outcome, and a spend monitor (4.28.0; ADR-042).

Prices are assumptions, not facts. The table is Chapter 10's (the agent runtime's budget module, dated 2027-01-12),
with the same values; `tests/test_routing_costs.py` fails if the two tables drift apart. Two assumptions
are added here and must be checked before any live use:

- Reasoning tokens a model generates before its answer are billed as output tokens, even when they are not
  shown. `sim-reasoner` stands in for a large model run with extended reasoning, at the large model's prices.
- Writing a prompt prefix to a provider's cache costs CACHE_WRITE_MULTIPLIER (1.25) times the input price,
  the surcharge some providers charge for a five-minute cache entry; reads cost 5% of the input price.
  Chapter 10's table left the write surcharge out.

Cost per call is the wrong number to watch. A call that times out is still billed, and its answer is thrown
away; a call that returns an invalid answer is billed and retried. `cost_per_success` divides everything
spent by the outcomes that were good, which is the number a budget and an alert should use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PRICES_AS_OF = "2027-01-12"
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Cache read is input read from a provider's prompt cache."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float

    @property
    def cache_write_per_mtok(self) -> float:
        return round(self.input_per_mtok * CACHE_WRITE_MULTIPLIER, 6)


# Assumed list prices as of PRICES_AS_OF; verify before use. sim-* are simulated models carrying the prices
# of the live models they stand in for (Chapter 2's table).
PRICES = {
    "sim-large": Price(4.00, 20.00, 0.20),
    "sim-reasoner": Price(4.00, 20.00, 0.20),
    "sim-small": Price(0.10, 0.50, 0.005),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
}


def call_cost(price: Price, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
              cache_write_tokens: int = 0) -> float:
    """USD for one call. Output includes reasoning tokens. Cache reads and writes are parts of the input."""
    if min(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens) < 0:
        raise ValueError("token counts must be non-negative")
    if cache_read_tokens + cache_write_tokens > input_tokens:
        raise ValueError("cached and cache-written tokens are parts of the input")
    plain = input_tokens - cache_read_tokens - cache_write_tokens
    return (plain * price.input_per_mtok + cache_read_tokens * price.cache_read_per_mtok
            + cache_write_tokens * price.cache_write_per_mtok + output_tokens * price.output_per_mtok) / 1e6


def cost_per_success(costs: Iterable[float], successes: int) -> float:
    """Everything spent, including failed, timed-out and retried calls, divided by the good outcomes."""
    total = sum(costs)
    if successes < 0:
        raise ValueError("successes must be non-negative")
    return total / successes if successes else float("inf")


@dataclass(frozen=True)
class Alert:
    day: str
    kind: str      # "cost_per_success" or "daily_spend"
    value: float
    limit: float


@dataclass(frozen=True)
class SpendMonitor:
    """Daily checks on one feature's spend.

    "Successes" is whatever good-outcome count is available daily. Correctness labels arrive late (people's
    confirmations and a weekly sample), so a daily check usually runs on suggestions delivered, and a weekly one
    on correct outcomes.

    baseline_per_success: the cost per success the feature was approved at (from its gate record)
    tolerance:            the rise that alerts; 0.25 matches Chapter 7's cost warning
    window_days:          days pooled for cost per success, so one quiet day does not alert
    daily_ceiling_usd:    a hard daily spend figure that alerts on its own
    min_successes:        a window with fewer successes is not judged on cost per success
    """

    baseline_per_success: float
    tolerance: float = 0.25
    window_days: int = 3
    daily_ceiling_usd: float | None = None
    min_successes: int = 50

    def check(self, days: list[tuple[str, float, int]]) -> list[Alert]:
        """`days` is [(day, usd, successes)] in date order. Returns every alert, in order."""
        alerts = []
        limit = self.baseline_per_success * (1 + self.tolerance)
        for i, (day, usd, _) in enumerate(days):
            if self.daily_ceiling_usd is not None and usd > self.daily_ceiling_usd:
                alerts.append(Alert(day, "daily_spend", round(usd, 6), self.daily_ceiling_usd))
            window = days[max(0, i - self.window_days + 1): i + 1]
            spent, good = sum(d[1] for d in window), sum(d[2] for d in window)
            if good >= self.min_successes and spent / good > limit:
                alerts.append(Alert(day, "cost_per_success", round(spent / good, 6), round(limit, 6)))
        return alerts
