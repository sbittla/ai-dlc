"""Budgets for agent runs: steps, model calls, money and time (added in 4.24.0; ADR-024).

A budget belongs to a run, not to a process. The meter's totals are saved in the run's checkpoint, so a
run that crashes and resumes continues from what it had already spent, and a restart can never reset
the ceiling.

Two checks guard the ceiling. `check` refuses to start another step once any limit has been reached.
`admit` refuses a model call whose estimated cost would take the run past its money limit. The loop computes
the estimate itself, from the request's input size and its output allowance, so a call can overshoot only if
the provider bills more than that allowance; such a call is counted in `overruns`. A time limit can still be
passed by the duration of the last step, because a step's time is known only when it ends.

Prices are assumptions, not facts: list prices change. The table records the date it was written and
must be checked before any live run. Simulated models carry the prices of the live models they stand
in for (Chapter 2's table).
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRICES_AS_OF = "2027-01-12"


@dataclass(frozen=True)
class Price:
    """USD per million tokens. Cached input is input read from a provider's prompt cache."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float


# Assumed list prices as of PRICES_AS_OF (Lab 2.1's table); verify before use. Cache reads are 5% of the input
# price. Some providers also charge more than the input price to write a prompt to the cache; that surcharge
# is not modelled here, so cached runs are slightly cheaper than they would be.
DEFAULT_PRICES = {
    "sim-large": Price(4.00, 20.00, 0.20),
    "sim-small": Price(0.10, 0.50, 0.005),
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
}

LIMITS = ("steps", "model_calls", "usd", "seconds")


@dataclass(frozen=True)
class Budget:
    """Ceilings for one run. A step is one model call or one tool call."""

    max_steps: int
    max_usd: float
    max_seconds: float
    max_model_calls: int | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1 or self.max_usd <= 0 or self.max_seconds <= 0:
            raise ValueError("every budget limit must be positive")
        if self.max_model_calls is not None and self.max_model_calls < 1:
            raise ValueError("max_model_calls must be positive")


class BudgetExceeded(Exception):
    """A limit was reached. `kind` is one of LIMITS; it is what the run's stop reason records."""

    def __init__(self, kind: str, used: float, limit: float) -> None:
        super().__init__(f"budget: {kind} {used:g} of {limit:g}")
        self.kind = kind
        self.used = used
        self.limit = limit


def cost_usd(price: Price, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    """Cost of one call. `cached_tokens` is the part of `input_tokens` read from the cache."""
    if not 0 <= cached_tokens <= input_tokens or output_tokens < 0:
        raise ValueError("token counts must be non-negative, and cached tokens part of the input")
    fresh = input_tokens - cached_tokens
    return (fresh * price.input_per_mtok + cached_tokens * price.cache_read_per_mtok
            + output_tokens * price.output_per_mtok) / 1e6


@dataclass
class Meter:
    """What a run has used so far, by actor (agent) as well as in total."""

    budget: Budget
    prices: dict[str, Price] = field(default_factory=lambda: dict(DEFAULT_PRICES))
    steps: int = 0
    model_calls: int = 0
    usd: float = 0.0
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    by_actor: dict[str, float] = field(default_factory=dict)
    overruns: int = 0  # model calls that cost more than the estimate they were admitted on

    def used(self, kind: str) -> float:
        return {"steps": self.steps, "model_calls": self.model_calls, "usd": self.usd,
                "seconds": self.seconds}[kind]

    def limit(self, kind: str) -> float | None:
        return {"steps": self.budget.max_steps, "model_calls": self.budget.max_model_calls,
                "usd": self.budget.max_usd, "seconds": self.budget.max_seconds}[kind]

    def check(self) -> None:
        """Raise BudgetExceeded for the first limit, in LIMITS order, whose use has reached it.

        A limit of None is not checked. Reaching a limit (used >= limit) is enough: the run may not
        start another step.
        """
        for kind in LIMITS:
            limit = self.limit(kind)
            if limit is not None and self.used(kind) >= limit:
                raise BudgetExceeded(kind, self.used(kind), limit)

    def admit(self, estimated_usd: float) -> None:
        """Call `check`, then refuse a call whose estimate would take spend past max_usd.

        Raises BudgetExceeded("usd", usd + estimated_usd, max_usd) in that case.
        """
        self.check()
        if self.usd + estimated_usd > self.budget.max_usd:
            raise BudgetExceeded("usd", self.usd + estimated_usd, self.budget.max_usd)

    def estimate(self, model: str, input_tokens: int, max_output_tokens: int, cached_tokens: int = 0) -> float:
        """An upper estimate: the whole output budget at the output price."""
        return cost_usd(self.prices[model], input_tokens, max_output_tokens, cached_tokens)

    def charge_model(self, actor: str, model: str, input_tokens: int, output_tokens: int, seconds: float,
                     cached_tokens: int = 0) -> float:
        cost = cost_usd(self.prices[model], input_tokens, output_tokens, cached_tokens)
        self.steps += 1
        self.model_calls += 1
        self.usd += cost
        self.seconds += seconds
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached_tokens
        self.by_actor[actor] = self.by_actor.get(actor, 0.0) + cost
        return cost

    def charge_tool(self, actor: str, seconds: float) -> None:
        self.steps += 1
        self.seconds += seconds
        self.by_actor.setdefault(actor, 0.0)

    def snapshot(self) -> dict:
        """The totals, for a checkpoint. `restore` reads them back."""
        return {"steps": self.steps, "model_calls": self.model_calls, "usd": self.usd, "seconds": self.seconds,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cached_tokens": self.cached_tokens, "by_actor": dict(self.by_actor), "overruns": self.overruns}

    def restore(self, data: dict) -> None:
        for name in ("steps", "model_calls", "usd", "seconds", "input_tokens", "output_tokens", "cached_tokens",
                     "overruns"):
            setattr(self, name, data.get(name, 0))
        self.by_actor = dict(data.get("by_actor", {}))
