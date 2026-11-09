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

Copied from Lab 7.1 (labs/ch07/L7.1-triage-eval-gate/solution/evalsuite/models.py)
without its live adapter. Lab 17.2 adds one CONFIGURED profile, `sim-reasoner`
with `triage-v3.1`: a stand-in for a large model run with extended reasoning,
in the same family as `sim-large` (so paired comparisons share per-ticket
randomness) and at its prices. Its accuracy was set so that it gets about half
as many held-out tickets wrong as `sim-large` does; that is the "doubled
quality" of Chapter 17's opening incident, configured here, not discovered.
How long it reasons, and so how long it takes, is configured in data/models.json.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from typing import Protocol



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
    # Lab 17.2 (configured): the opening incident's model.
    ("sim-reasoner", "triage-v3.1"): _p(0.99, 0.92, 0.90, 0.94, 0.92, 0.96, invalid=0.005, inj=0.01),
}

# Models in the same family share their per-ticket randomness, so a prompt
# change or an upgrade within a family changes answers only where the
# configured accuracy differs. That is what makes paired comparisons sharp.
FAMILY = {"sim-large": "large", "sim-large-2": "large", "sim-reasoner": "large", "sim-small": "small"}
PRICES = {"sim-large": (4.00, 20.00), "sim-large-2": (4.00, 20.00), "sim-reasoner": (4.00, 20.00), "sim-small": (0.10, 0.50)}
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
