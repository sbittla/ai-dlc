"""The two hooks ADR-043 adds to the service and the worker, as they will be merged (4.28.0 merge note).

Chapter 17 owns `relay.routing`, not `relay.service` or `relay.worker`, so 4.28.0 ships the hooks here and
`tests/test_routing_hooks.py` runs them on the real service and worker. At the canonical merge:

1. Service: `QuotaRelayApp.create_job` below is `RelayApp.create_job` with the five lines marked HOOK added
   just before the job is queued, and `RelayApp.__init__` gains `quota=None, triage_estimate_usd=0.0`.
   `test_the_service_hook_is_the_current_method_plus_the_hook` checks the copy against the source.
2. Worker: `MeteredTriage` moves to `src/relay/worker/metered.py`, and `relay/worker/__main__.py` wraps its
   `SimulatedTriage()` in it when the deployment configures a quota database.
"""

from __future__ import annotations

import itertools
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from relay.routing import PRICES, SpendQuota, call_cost
from relay.service import RelayApp
from relay.service.app import IDEMPOTENCY_KEY, MAX_TICKET_CHARS, job_view
from relay.service.responses import Response, error, read_json
from relay.worker import IdempotencyConflict
from relay.worker.triage import TriageOutcome

HOOK_LINES = 5


class QuotaRelayApp(RelayApp):
    def __init__(self, *args, quota: SpendQuota, triage_estimate_usd: float, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.quota, self.triage_estimate_usd = quota, triage_estimate_usd

    def create_job(self, user, environ: dict, now: float) -> Response:
        if user.role == "Guest":
            return error(403, "forbidden")
        key = environ.get("HTTP_IDEMPOTENCY_KEY", "")
        if not IDEMPOTENCY_KEY.match(key):
            return error(400, "Idempotency-Key header required: 8-64 characters from A-Z, a-z, 0-9, - and _")
        body, problem = read_json(environ)
        if problem is not None:
            return problem
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip() or set(body) != {"text"}:
            return error(400, 'body must be {"text": "<ticket text>"}')
        if len(text) > MAX_TICKET_CHARS:
            return error(413, f"ticket text over {MAX_TICKET_CHARS} characters")
        if self.quota is not None:  # HOOK (ADR-043): what this caller may make Relay spend on triage today
            who = [f"user:{user.id}", f"workspace:{self.directory.workspace}"]  # HOOK
            decision = self.quota.reserve(who, self.triage_estimate_usd, now, f"job:{who[1]}:{key}")  # HOOK
            if not decision.allowed:  # HOOK
                return error(429, "triage spend quota reached", **{"Retry-After": str(decision.retry_after_s)})  # HOOK
        try:
            job, created = self.queue.enqueue(self.directory.workspace, key, text, now)
        except IdempotencyConflict:
            return error(422, "Idempotency-Key already used with a different body")
        headers = {"Location": f"/v1/triage-jobs/{job.id}"}
        if not created:
            headers["Idempotent-Replayed"] = "true"
        return Response(202, job_view(job), headers)


def estimate_tokens(text: str) -> int:
    """One token per four characters, as Labs 2.1 and 7.1 estimate; the live adapter reads the real usage."""
    return max(1, len(text) // 4)


@dataclass
class MeteredTriage:
    """A TriageClient that reserves a call's worst-case cost before it, and settles the actual cost after.

    The estimate is the route's ceiling: the prompt and ticket at one token per four characters, plus
    `max_output_tokens`. A refused reservation returns error "quota": the worker retries it with backoff and
    then hands the job to a person (`needs_human`), so a spent quota never drops a ticket or guesses a label.
    """

    inner: object
    quota: SpendQuota
    prompt_chars: int
    max_output_tokens: int
    principals: tuple[str, ...] = ("agent:triage-worker", "feature:triage")
    clock: Callable[[], float] = time.time
    refused: int = field(default=0)
    _nonce: str = field(default_factory=lambda: os.urandom(8).hex(), repr=False)
    _calls: itertools.count = field(default_factory=itertools.count, repr=False)

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def prompt(self) -> str:
        return self.inner.prompt

    def classify(self, ticket_text: str, attempt: int) -> TriageOutcome:
        price = PRICES[self.inner.model]
        tokens_in = max(1, (self.prompt_chars + len(ticket_text)) // 4)
        # Every call is new money, so every reservation gets its own ref. A ref built from the ticket text would
        # make a second ticket with the same text look like a replay, and it would never be charged.
        ref = f"call:{self._nonce}:{next(self._calls)}:{attempt}"
        decision = self.quota.reserve(list(self.principals), call_cost(price, tokens_in, self.max_output_tokens),
                                      self.clock(), ref)
        if not decision.allowed:
            self.refused += 1
            return TriageOutcome("", 0.0, "quota")
        outcome = self.inner.classify(ticket_text, attempt)
        actual = 0.0 if outcome.error == "unavailable" else call_cost(price, tokens_in, estimate_tokens(outcome.text))
        self.quota.settle(ref, actual, self.clock())
        return outcome
