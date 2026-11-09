"""Model routes with token limits and timeouts, and the policy that picks one (4.28.0; ADR-042).

A route is a model, a prompt version, an output-token limit and a timeout. The limit counts every output
token, reasoning included, so it bounds both the cost and the duration of a call. The timeout is how long the
caller waits before it gives up; a call that runs past it has usually been billed already, so its answer is
paid for and thrown away. That is what happened in Chapter 17's opening incident, where a reasoning model's
long answers met the worker's 10-second timeout. `route_problems` checks the two settings against a measured
latency profile before a route is used.

The policy routes on a difficulty score computed before the call (Chapter 7's router): at or above the
threshold the ticket takes the `hard` route, otherwise the `default` one. Invalid output on the hard route
falls back to the default route once. The score never comes from the ticket's own claims of urgency alone;
that is Chapter 7's router's business, and it is evaluated there.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    name: str
    model: str
    prompt: str
    max_output_tokens: int
    timeout_s: float

    def __post_init__(self) -> None:
        if self.max_output_tokens < 1 or self.timeout_s <= 0:
            raise ValueError("a route needs a positive token limit and timeout")


@dataclass(frozen=True)
class RoutePolicy:
    default: Route
    hard: Route | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        if (self.hard is None) != (self.threshold is None):
            raise ValueError("a hard route needs a threshold, and a threshold needs a hard route")

    def choose(self, score: float | None) -> Route:
        """The route for a ticket with this difficulty score (None: no score, so the default route)."""
        if self.hard is not None and score is not None and score >= self.threshold:
            return self.hard
        return self.default

    def fallback(self, route: Route) -> Route | None:
        """Where an invalid answer on `route` goes next: the default route, once; None from the default."""
        return self.default if route != self.default else None


def route_problems(route: Route, ttft_p99_s: float, output_tokens_per_s: float) -> list[str]:
    """Problems with a route's settings, given a measured latency profile of its model.

    The slowest call the token limit allows takes about ttft_p99_s + max_output_tokens / output_tokens_per_s.
    If that is longer than the timeout, the caller can give up on calls it has already paid for.
    """
    if ttft_p99_s < 0 or output_tokens_per_s <= 0:
        raise ValueError("latency profile must be non-negative, with a positive output rate")
    worst = ttft_p99_s + route.max_output_tokens / output_tokens_per_s
    if worst > route.timeout_s:
        return [f"{route.name}: a call allowed {route.max_output_tokens} output tokens can take {worst:.1f} s, "
                f"past the {route.timeout_s:g} s timeout; lower the limit or raise the timeout"]
    return []
