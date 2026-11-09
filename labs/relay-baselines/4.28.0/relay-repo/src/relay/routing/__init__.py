"""Cost engineering for Relay's model calls (added in 4.28.0; ADR-042, ADR-043).

- `costs`: the dated price table, the cost of one call (reasoning tokens are billed as output), cost per
  successful outcome, and a spend monitor that compares cost per success with a baseline.
- `policy`: model routes with token limits and timeouts, a routing policy, and a check that a route's
  token limit cannot let a call run past its timeout (the opening incident of Chapter 17).
- `quota`: daily spend quotas per user, agent, workspace and feature, kept in a ledger that every process
  shares, with every refusal recorded (denial-of-wallet control).

Nothing in Relay calls this package yet. The service and the worker are wired to it by the hooks in
ADR-043 (a merge note for canonical 4.28.0); `tests/test_routing_hooks.py` runs those hooks on the real
service and worker. The package imports only the standard library and makes no network calls.
"""

from .costs import (CACHE_WRITE_MULTIPLIER, PRICES, PRICES_AS_OF, Alert, Price, SpendMonitor, call_cost,
                    cost_per_success)
from .policy import Route, RoutePolicy, route_problems
from .quota import QUOTA_SCHEMA, Decision, QuotaLimits, SpendQuota

__all__ = ["CACHE_WRITE_MULTIPLIER", "PRICES", "PRICES_AS_OF", "QUOTA_SCHEMA", "Alert", "Decision", "Price",
           "QuotaLimits", "Route", "RoutePolicy", "SpendMonitor", "SpendQuota", "call_cost", "cost_per_success",
           "route_problems"]
