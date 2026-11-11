"""The triage call, simulated.

Relay's production triage sends a ticket to a hosted model with the adopted
prompt (`triage-v3.1`, Chapter 7) and gets back a category, a priority and a
team. This snapshot makes no model calls. `SimulatedTriage` stands in for the
model with the three behaviours an architecture has to survive: it is slow
(a latency drawn around a median), sometimes wrong or unusable (invalid
output), and sometimes unavailable (timeouts and errors). Every draw is
seeded by the ticket text and the attempt number, so a run is repeatable.

It is NOT a model, and its labels come from keyword rules. Use it to
exercise the worker, never to judge triage quality; Chapters 2 and 7 do that.

From 4.26.0 (ADR-032) the worker sends ticket text inside a spotlighting
envelope (`relay.worker.untrusted.mark`). The simulator reads the text out of
the envelope, draws exactly as it did before, and obeys an embedded instruction
at `marked_injection_rate` instead of `injection_rate`. Both rates are
configured, not measured: they let tests show a lowered obedience, never how
much a real model's obedience falls. `SimulatedSummarizer` stands in for the
model that writes the triage summary, with the same caveat.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from typing import Protocol

from .untrusted import unmark

CATEGORIES = ("bug", "feature_request", "billing", "access", "how_to")
PRIORITIES = ("P1", "P2", "P3", "P4")
TEAMS = ("platform", "payments", "identity", "docs")

# (words that trigger the rule, category, priority, team), first match wins
_RULES = (
    (("500 error", "outage", "is down", "nothing loads", "data loss"), "bug", "P1", "platform"),
    (("charged", "invoice", "refund", "card", "billing"), "billing", "P2", "payments"),
    (("log in", "login", "sso", "password", "locked out"), "access", "P2", "identity"),
    (("how do i", "how to", "where can i", "is there a way"), "how_to", "P3", "docs"),
    (("could you add", "feature request", "it would be great", "please add"), "feature_request", "P4", "platform"),
)
_INJECTION_MARKERS = ("ignore previous", "ignore all previous", "mark this ticket p1", "as the ai")


@dataclass(frozen=True)
class TriageOutcome:
    """What one attempt returned: raw text (to be validated), latency, or an error."""

    text: str
    latency_s: float
    error: str | None = None  # "timeout" or "unavailable"; None if text came back


class TriageClient(Protocol):
    model: str
    prompt: str

    def classify(self, ticket_text: str, attempt: int) -> TriageOutcome: ...


@dataclass(frozen=True)
class SimulatedTriage:
    """A seeded stand-in for the triage model (see the module docstring).

    latency_median_s: median latency; draws are log-normal around it
    invalid_rate:     probability the output is not valid JSON of the right shape
    unavailable_rate: probability the call fails outright
    injection_rate:   probability of obeying an instruction embedded in the ticket
    marked_injection_rate: the same, when the ticket arrives inside a spotlighting envelope
    """

    model: str = "sim-large"
    prompt: str = "triage-v3.1"
    latency_median_s: float = 2.4
    invalid_rate: float = 0.02
    unavailable_rate: float = 0.03
    injection_rate: float = 0.10
    marked_injection_rate: float = 0.02
    seed: int = 6

    def _rng(self, ticket_text: str, attempt: int, stream: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}|{stream}|{attempt}|{ticket_text}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    def classify(self, ticket_text: str, attempt: int) -> TriageOutcome:
        ticket_text, marked = unmark(ticket_text)
        obey_rate = self.marked_injection_rate if marked else self.injection_rate
        rng = self._rng(ticket_text, attempt, "call")
        latency = round(self.latency_median_s * math.exp(rng.gauss(0, 0.35)), 3)
        if rng.random() < self.unavailable_rate:
            return TriageOutcome("", latency, "unavailable")
        label = keyword_label(ticket_text)
        lowered = ticket_text.lower()
        if any(m in lowered for m in _INJECTION_MARKERS):
            if self._rng(ticket_text, attempt, "injection").random() < obey_rate:
                label = {"category": "feature_request", "priority": "P1", "team": "payments"}
        confidence = round(0.55 + 0.42 * self._rng(ticket_text, 0, "confidence").random(), 2)
        if rng.random() < self.invalid_rate:
            return TriageOutcome("Sure! Here is the triage result: " + json.dumps(label), latency)
        return TriageOutcome(json.dumps({**label, "confidence": confidence}), latency)


def keyword_label(ticket_text: str) -> dict:
    lowered = ticket_text.lower()
    for words, category, priority, team in _RULES:
        if any(w in lowered for w in words):
            return {"category": category, "priority": priority, "team": team}
    return {"category": "bug", "priority": "P3", "team": "platform"}


def parse_suggestion(text: str) -> tuple[dict | None, str | None]:
    """Validate a triage response. Returns (suggestion, None) or (None, reason).

    The response must be a JSON object with exactly category, priority, team and
    confidence, each from its allowed set; confidence is a number from 0 to 1.
    Nothing is repaired: prose around the JSON is a failure, as in Chapter 2.
    """
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None, "invalid_json"
    if not isinstance(value, dict) or set(value) != {"category", "priority", "team", "confidence"}:
        return None, "schema"
    allowed = {"category": CATEGORIES, "priority": PRIORITIES, "team": TEAMS}
    if any(value[k] not in v for k, v in allowed.items()):
        return None, "schema"
    conf = value["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return None, "schema"
    return value, None


class Summarizer(Protocol):
    model: str

    def summarize(self, ticket_text: str, attempt: int) -> str: ...


_SUMMARY_INJECTIONS = ("in your summary", "include this image", "summary must", "append this", "when you summarise",
                       "when you summarize")


@dataclass(frozen=True)
class SimulatedSummarizer:
    """A seeded stand-in for the model that writes a one-paragraph summary for support staff.

    It returns the ticket's first sentence, prefixed. If the ticket asks for something to go into the
    summary, it obeys at `injection_rate` (or `marked_injection_rate` inside an envelope) and appends the
    attacker's text, which is what the February 2027 incident's prototype did with a Markdown image.
    Configured rates, as for SimulatedTriage.
    """

    model: str = "sim-large"
    injection_rate: float = 0.60
    marked_injection_rate: float = 0.12
    seed: int = 6

    def summarize(self, ticket_text: str, attempt: int) -> str:
        text, marked = unmark(ticket_text)
        first = " ".join(text.split(". ")[0].split())[:200]
        summary = f"Customer reports: {first.rstrip('.')}."
        lowered = text.lower()
        hit = next((m for m in _SUMMARY_INJECTIONS if m in lowered), None)
        if hit is not None:
            digest = hashlib.sha256(f"{self.seed}|summary|{attempt}|{text}".encode()).hexdigest()
            if random.Random(int(digest[:16], 16)).random() < (self.marked_injection_rate if marked
                                                               else self.injection_rate):
                start = lowered.index(hit) + len(hit)
                summary += " " + " ".join(text[start:].split(". ")[0].split()).strip(" :")
        return summary
