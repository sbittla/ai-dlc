"""Model clients: two simulated models (default) and an optional live Claude adapter.

The simulated models let everyone run the lab offline, for free, with
identical results. They are NOT real models. They are seeded random
processes whose accuracy, formatting errors, latency and token use are set to
plausible values, so you can practise building and reading an evaluation
before spending money on one. The live adapter runs the same harness
against real Claude models when you have credentials and a budget.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Protocol

from .schema import TRIAGE_SCHEMA


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    stop_reason: str = "end_turn"


class ModelClient(Protocol):
    name: str
    price_in_per_mtok: float   # USD per million input tokens
    price_out_per_mtok: float  # USD per million output tokens

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion: ...


# ------------------------------------------------------------------ simulated

ALTERNATIVES = {
    "category": ["bug", "feature_request", "billing", "access", "how_to"],
    "priority": ["P1", "P2", "P3", "P4"],
    "team": ["platform", "payments", "identity", "docs"],
}

INJECTED = {"category": "feature_request", "priority": "P1", "team": "payments"}


@dataclass
class SimulatedModel:
    """A seeded stand-in for a model. Behaviour per (ticket, run) is deterministic.

    accuracy:        probability of a fully correct label, by ticket difficulty
    invalid_rate:    probability the output is not valid against the schema
    injection_rate:  probability of obeying instructions embedded in the ticket
    """

    name: str
    gold: dict[str, dict]            # ticket id -> {"difficulty", "expected", "injection"}
    accuracy: dict[str, float]
    invalid_rate: float
    injection_rate: float
    latency_median_s: float
    price_in_per_mtok: float
    price_out_per_mtok: float
    seed: int = 11
    _calls: int = field(default=0, init=False)

    def _rng(self, ticket_id: str, run: int) -> random.Random:
        return random.Random(f"{self.seed}|{self.name}|{ticket_id}|{run}")

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        self._calls += 1
        rng = self._rng(ticket_id, run)
        info = self.gold[ticket_id]
        label = dict(info["expected"])

        # Separate random stream for the injection decision, so it does not
        # shift every other draw for the ticket.
        inj_rng = random.Random(f"{self.seed}|{self.name}|{ticket_id}|{run}|injection")
        if info.get("injection") and inj_rng.random() < self.injection_rate:
            label = dict(INJECTED)
        elif rng.random() > self.accuracy[info["difficulty"]]:
            # Wrong on one field, usually priority (the most subjective field).
            fld = rng.choices(["priority", "category", "team"], weights=[0.5, 0.3, 0.2])[0]
            label[fld] = rng.choice([v for v in ALTERNATIVES[fld] if v != label[fld]])

        text = json.dumps(label)
        if rng.random() < self.invalid_rate:
            mode = rng.choice(["prose", "missing", "enum"])
            if mode == "prose":
                text = "Sure! Here is the triage result:\n" + text
            elif mode == "missing":
                label.pop("team")
                text = json.dumps(label)
            else:
                label["priority"] = "urgent"
                text = json.dumps(label)

        input_tokens = (len(system) + len(user)) // 4
        output_tokens = len(text) // 4 + rng.randint(0, 4)
        latency = self.latency_median_s * math.exp(rng.gauss(0, 0.35))
        return Completion(text, input_tokens, output_tokens, round(latency, 3))


def simulated_models(gold: dict[str, dict]) -> dict[str, SimulatedModel]:
    """The two simulated models used in the chapter.

    Prices mirror published list prices for a large and a small model at the
    time of writing (see the chapter's "What changes next" box); treat them
    as assumptions to replace with current prices.
    """
    return {
        "sim-large": SimulatedModel(
            name="sim-large", gold=gold, accuracy={"easy": 0.97, "hard": 0.82},
            invalid_rate=0.01, injection_rate=0.10, latency_median_s=2.4,
            price_in_per_mtok=4.00, price_out_per_mtok=20.00,
        ),
        "sim-small": SimulatedModel(
            name="sim-small", gold=gold, accuracy={"easy": 0.93, "hard": 0.58},
            invalid_rate=0.05, injection_rate=0.80, latency_median_s=0.6,
            price_in_per_mtok=0.10, price_out_per_mtok=0.50,
        ),
    }


# ------------------------------------------------------------------ live

@dataclass
class ClaudeModel:
    """Live adapter for Claude models via the official Anthropic Python SDK.

    Requires `pip install anthropic` and credentials (ANTHROPIC_API_KEY, or an
    `ant auth login` profile). Uses structured outputs so the response is
    constrained to TRIAGE_SCHEMA; the harness still validates it, because
    defence in depth is the point of the lab.

    Deliberately does NOT enable server-side refusal fallbacks: an evaluation
    must know which model produced each answer. Refusals are recorded as
    failures with stop_reason "refusal".
    """

    name: str  # an exact model ID, e.g. "claude-opus-5-5" or "claude-haiku-5-5"
    price_in_per_mtok: float
    price_out_per_mtok: float
    effort: str = "low"  # classification rarely benefits from higher effort; measure it
    max_tokens: int = 1024  # the most output (thinking included) one call can be billed for
    _client: object = field(default=None, init=False, repr=False)

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        import anthropic  # imported lazily so offline runs need no package

        if self._client is None:
            self._client = anthropic.Anthropic()
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self.name,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": TRIAGE_SCHEMA},
                },
            )
        except anthropic.APIError as exc:
            # After the SDK's own retries. Record the failure instead of losing the run.
            return Completion("", 0, 0, round(time.perf_counter() - started, 3), stop_reason=f"api_error:{type(exc).__name__}")
        latency = time.perf_counter() - started
        text = next((b.text for b in response.content if b.type == "text"), "")
        return Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=round(latency, 3),
            stop_reason=response.stop_reason or "",
        )


LIVE_PRICES = {  # USD per million tokens (input, output); verify before use
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def live_model(model_id: str) -> ClaudeModel:
    if model_id not in LIVE_PRICES:
        raise ValueError(f"add a price for {model_id} to LIVE_PRICES first")
    p_in, p_out = LIVE_PRICES[model_id]
    return ClaudeModel(name=model_id, price_in_per_mtok=p_in, price_out_per_mtok=p_out)


# ------------------------------------------------------------------ spend guard

CHARS_PER_TOKEN_PESSIMISTIC = 2  # real tokenizers average 3-4 characters per token; assume fewer


def worst_case_call_usd(system: str, user: str, price_in_per_mtok: float, price_out_per_mtok: float,
                        max_tokens: int) -> float:
    """The most one call can cost: input (prompt and schema) at one token per 2 characters, and
    every output token up to max_tokens billed. Deliberately pessimistic, so a guard built on it
    stops before the ceiling instead of after it."""
    chars = len(system) + len(user) + len(json.dumps(TRIAGE_SCHEMA))
    input_tokens = math.ceil(chars / CHARS_PER_TOKEN_PESSIMISTIC)
    return input_tokens / 1_000_000 * price_in_per_mtok + max_tokens / 1_000_000 * price_out_per_mtok


@dataclass
class BudgetGuard:
    """Wraps a live client and refuses any call whose worst-case cost would take spend past max_usd.

    The check runs before the call, so spend never passes the ceiling (as long as the worst-case
    estimate holds). A refused call makes no request and is returned with stop_reason
    "budget_exceeded", so the runner records it as a failure of kind "budget" instead of losing it.
    """

    inner: ClaudeModel
    max_usd: float
    spent_usd: float = 0.0
    refused: int = 0

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def price_in_per_mtok(self) -> float:
        return self.inner.price_in_per_mtok

    @property
    def price_out_per_mtok(self) -> float:
        return self.inner.price_out_per_mtok

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        worst = worst_case_call_usd(system, user, self.price_in_per_mtok, self.price_out_per_mtok,
                                    self.inner.max_tokens)
        if self.spent_usd + worst > self.max_usd:
            self.refused += 1
            return Completion("", 0, 0, 0.0, stop_reason="budget_exceeded")
        c = self.inner.complete(system, user, ticket_id, run)
        self.spent_usd += (c.input_tokens * self.price_in_per_mtok
                           + c.output_tokens * self.price_out_per_mtok) / 1_000_000
        return c


def guarded_live_models(model_ids: list[str], max_usd: float) -> list[BudgetGuard]:
    """One guard per model, each with an equal share of max_usd, so the first model cannot use
    the whole budget and leave nothing for the second."""
    share = max_usd / len(model_ids)
    return [BudgetGuard(live_model(m), share) for m in model_ids]
