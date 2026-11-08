"""Model clients: simulated triage models (default), a live Claude adapter, and a budget guard.

The simulated models are NOT real models. They are seeded random processes
whose behaviour is CONFIGURED in PROFILES below: how often each model is
right on each kind of ticket under each prompt version, how often it breaks
the schema, and how often it obeys an injected instruction. Every pattern
the lab's reports show (the triage-v2 regression, the German slice of
sim-large-2, the small model's weakness on hard tickets) was put there to
be found. What transfers to real models is the method, not the numbers.

The simulator is configured separately from Lab 2.1's, so its results on
the 40 Chapter 2 tickets differ from Table 2.6.

The live adapter is copied from Lab 2.1 (labs/ch02/L2.1-model-eval-harness/
solution/harness/models.py) and runs the same suite against real Claude
models when you have credentials and a budget.
"""

from __future__ import annotations

import json
import math
import random
import re
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
    served_by: str = ""  # the model that answered (differs from the client name when routed)
    extra_cost_usd: float = 0.0  # cost of an earlier attempt this answer replaced (routing fallback)


class ModelClient(Protocol):
    name: str

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion: ...

    def cost_usd(self, c: Completion) -> float: ...


def _cost(c: Completion, price_in: float, price_out: float) -> float:
    return c.input_tokens / 1_000_000 * price_in + c.output_tokens / 1_000_000 * price_out


# ------------------------------------------------------------------ simulated

ALTERNATIVES = {
    "category": ["bug", "feature_request", "billing", "access", "how_to"],
    "priority": ["P1", "P2", "P3", "P4"],
    "team": ["platform", "payments", "identity", "docs"],
}


@dataclass(frozen=True)
class Profile:
    """Configured behaviour of one simulated model under one prompt version."""

    accuracy: dict[str, float]          # P(fully correct label) by ticket kind
    language_shift: dict[str, float]    # added to accuracy for tickets in that language
    invalid_rate: float                 # P(output breaks the schema)
    injection_rate: float               # P(obeying an instruction embedded in the ticket)


def _p(plain, ambiguous, multi, over, under, adv, invalid, inj, lang=None) -> Profile:
    return Profile({"plain": plain, "ambiguous": ambiguous, "multi_issue": multi, "overstated": over,
                    "understated": under, "adversarial": adv}, lang or {}, invalid, inj)


# (model, prompt version) -> configured behaviour. Only these pairs exist.
PROFILES: dict[tuple[str, str], Profile] = {
    ("sim-large", "triage-v1"): _p(0.97, 0.80, 0.78, 0.86, 0.70, 0.92, invalid=0.01, inj=0.02),
    ("sim-large", "triage-v1.1"): _p(0.97, 0.79, 0.79, 0.86, 0.71, 0.92, invalid=0.01, inj=0.02),
    ("sim-large", "triage-v2"): _p(0.97, 0.80, 0.78, 0.30, 0.92, 0.92, invalid=0.01, inj=0.25),
    ("sim-large", "triage-v3"): _p(0.97, 0.81, 0.79, 0.88, 0.80, 0.92, invalid=0.01, inj=0.02),
    ("sim-large", "triage-v3.1"): _p(0.97, 0.81, 0.79, 0.88, 0.80, 0.92, invalid=0.01, inj=0.02),
    ("sim-large-2", "triage-v1"): _p(0.98, 0.86, 0.84, 0.90, 0.78, 0.94, invalid=0.005, inj=0.02,
                                     lang={"de": -0.20}),
    ("sim-small", "triage-v1"): _p(0.93, 0.55, 0.50, 0.60, 0.45, 0.70, invalid=0.05, inj=0.60),
}

# Models in the same family share their per-ticket randomness, so a prompt
# change or an upgrade within a family changes answers only where the
# configured accuracy differs. That is what makes paired comparisons sharp.
FAMILY = {"sim-large": "large", "sim-large-2": "large", "sim-small": "small"}
PRICES = {"sim-large": (4.00, 20.00), "sim-large-2": (4.00, 20.00), "sim-small": (0.10, 0.50)}
PERSISTENCE = 0.6  # share of a ticket's randomness that repeats across runs


def _norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.lower()))


@dataclass
class SimulatedTriageModel:
    """A seeded stand-in for a model under one prompt. Deterministic per (ticket, run)."""

    name: str
    prompt_version: str
    gold: dict[str, dict]  # ticket id -> ticket (kind, language, expected, injection_target)
    seed: int = 7
    calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        key = (self.name, self.prompt_version)
        if key not in PROFILES:
            raise ValueError(f"no simulated profile is configured for {self.name} with {self.prompt_version}")
        self.profile = PROFILES[key]
        self.price_in, self.price_out = PRICES[self.name]

    def _u(self, *parts) -> float:
        return random.Random("|".join(str(p) for p in (self.seed, *parts))).random()

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        self.calls += 1
        t = self.gold[ticket_id]
        fam = FAMILY[self.name]
        label = dict(t["expected"])
        rng = random.Random(f"{self.seed}|{fam}|{ticket_id}|{run}|error")

        if _norm(t["text"]) in _norm(system):
            pass  # the ticket is one of the prompt's worked examples: the model copies its label
        elif t.get("injection_target") and self._u(fam, ticket_id, run, "inj") < self.profile.injection_rate:
            label.update(t["injection_target"])
        else:
            p = self.profile.accuracy[t["kind"]] + self.profile.language_shift.get(t["language"], 0.0)
            # Mixture of a per-ticket and a per-run draw: still uniform, so P(correct) = p exactly.
            u_ticket, u_run = self._u(fam, ticket_id, "ticket"), self._u(fam, ticket_id, run, "run")
            u = u_ticket if self._u(fam, ticket_id, run, "which") < PERSISTENCE else u_run
            if u > p:
                label = self._wrong(label, t["kind"], rng)

        text = json.dumps(label)
        if self._u(self.name, self.prompt_version, ticket_id, run, "format") < self.profile.invalid_rate:
            mode = rng.choice(["prose", "missing", "enum"])
            if mode == "prose":
                text = "Sure! Here is the triage result:\n" + text
            elif mode == "missing":
                text = json.dumps({k: v for k, v in label.items() if k != "team"})
            else:
                text = json.dumps({**label, "priority": "urgent"})
        input_tokens = (len(system) + len(user)) // 4
        output_tokens = len(text) // 4 + rng.randint(0, 4)
        return Completion(text, input_tokens, output_tokens, 0.0, served_by=self.name)

    @staticmethod
    def _wrong(label: dict, kind: str, rng: random.Random) -> dict:
        order = ALTERNATIVES["priority"]
        i = order.index(label["priority"])
        out = dict(label)
        if kind == "overstated" and i > 0:
            out["priority"] = rng.choice(order[:i])           # alarmed tone: priority too high
        elif kind == "understated" and i < 3:
            out["priority"] = rng.choice(order[i + 1:])       # calm tone: priority too low
        elif kind == "multi_issue":
            out["category"] = rng.choice([v for v in ALTERNATIVES["category"] if v != label["category"]])
            out["team"] = rng.choice([v for v in ALTERNATIVES["team"] if v != label["team"]])
        else:
            fld = rng.choices(["priority", "category", "team"], weights=[0.5, 0.3, 0.2])[0]
            out[fld] = rng.choice([v for v in ALTERNATIVES[fld] if v != label[fld]])
        return out

    def cost_usd(self, c: Completion) -> float:
        return _cost(c, self.price_in, self.price_out)


# ------------------------------------------------------------------ live

@dataclass
class ClaudeModel:
    """Live adapter for Claude models via the official Anthropic Python SDK (copied from Lab 2.1).

    Requires `pip install -e ".[live]"` and credentials (ANTHROPIC_API_KEY, or
    an `ant auth login` profile). Uses structured outputs so the response is
    constrained to TRIAGE_SCHEMA; the suite still validates it.

    Deliberately does NOT enable server-side refusal fallbacks: an evaluation
    must know which model produced each answer. Refusals, truncation and API
    errors are recorded as outcomes, never raised.
    """

    name: str  # an exact model ID, e.g. "claude-opus-5-5" or "claude-haiku-5-5"
    price_in_per_mtok: float
    price_out_per_mtok: float
    effort: str = "low"
    _client: object = field(default=None, init=False, repr=False)

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        import anthropic  # imported lazily so offline runs need no package

        if self._client is None:
            self._client = anthropic.Anthropic()
        started = time.perf_counter()
        try:
            response = self._client.messages.create(
                model=self.name,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": TRIAGE_SCHEMA},
                },
            )
        except anthropic.APIError as exc:
            # After the SDK's own retries. Record the failure instead of losing the run.
            return Completion("", 0, 0, round(time.perf_counter() - started, 3),
                              stop_reason=f"api_error:{type(exc).__name__}", served_by=self.name)
        latency = time.perf_counter() - started
        text = next((b.text for b in response.content if b.type == "text"), "")
        return Completion(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=round(latency, 3),
            stop_reason=response.stop_reason or "",
            served_by=self.name,
        )

    def cost_usd(self, c: Completion) -> float:
        return _cost(c, self.price_in_per_mtok, self.price_out_per_mtok)


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


@dataclass
class BudgetGuard:
    """Wraps a client and refuses calls once the spend would pass a ceiling.

    A refused call is returned as stop_reason "budget_exceeded" so that it is
    recorded, and the gate fails closed on an incomplete run.
    """

    inner: ModelClient
    max_usd: float
    est_call_usd: float
    spent_usd: float = 0.0

    @property
    def name(self) -> str:
        return self.inner.name

    def complete(self, system: str, user: str, ticket_id: str, run: int) -> Completion:
        if self.spent_usd + self.est_call_usd > self.max_usd:
            return Completion("", 0, 0, 0.0, stop_reason="budget_exceeded", served_by=self.inner.name)
        c = self.inner.complete(system, user, ticket_id, run)
        self.spent_usd += self.inner.cost_usd(c)
        return c

    def cost_usd(self, c: Completion) -> float:
        return self.inner.cost_usd(c)


def estimate_call_usd(system: str, mean_user_chars: float, price_in: float, price_out: float,
                      output_tokens: int = 400) -> float:
    """A deliberately pessimistic per-call estimate: input at one token per 4 characters,
    plus 400 output tokens to allow for reasoning tokens."""
    return math.ceil((len(system) + mean_user_chars) / 4) / 1_000_000 * price_in + output_tokens / 1_000_000 * price_out
