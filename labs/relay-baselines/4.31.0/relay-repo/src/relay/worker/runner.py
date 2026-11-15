"""The background worker: run an escalation pass, then claim a triage job, call triage, record a suggestion.

The worker never changes a task. It records a suggested category, priority
and team with a confidence, and a person confirms or overrides it (decision
D3 and ESC-N01 in Chapter 4's PRD). An injected ticket can therefore steer a
suggestion, but cannot by itself page anyone.

Each pass writes a heartbeat, so a stalled worker is visible from the
service's health endpoint within the stall threshold. From 4.22.0 a pass also
runs the escalation engine's evaluation pass (ADR-017). If that fails, the
heartbeat is not written: an evaluator that cannot run must look stalled, not
healthy, because a missed escalation is a missed page (ESC-N09).

From 4.26.0 (ADR-032) the ticket text goes to the model inside a spotlighting
envelope (`mark_input`, on by default), and a worker given a `summarizer` also
keeps a short summary for support staff. The summary must pass
`parse_summary`: plain text with no address, link, image or markup. One that
does not is dropped and its reason recorded; the suggestion is kept, because
a refused summary is not a failed triage.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

from .escalation import EscalationPasses
from .queue import TriageQueue
from .triage import Summarizer, TriageClient, parse_suggestion
from .untrusted import mark, parse_summary

LOG = logging.getLogger("relay.worker")
STALL_AFTER_S = 300.0  # five minutes without a pass, as ESC-N09 sets for the escalation evaluator


@dataclass
class Worker:
    queue: TriageQueue
    triage: TriageClient
    worker_id: str = "worker-1"
    lease_s: float = 60.0
    timeout_s: float = 10.0  # a response slower than this is treated as a timeout
    clock: Callable[[], float] = time.time
    realtime: bool = False  # True: actually wait for the simulated latency (for load tests)
    outcomes: dict[str, int] = field(default_factory=dict)
    escalation: EscalationPasses | None = None  # None: triage only, as in 4.19.0 to 4.21.0
    mark_input: bool = True  # 4.26.0: spotlighting envelope around ticket text (ADR-032)
    summarizer: Summarizer | None = None  # None: no summary, as before 4.26.0
    secret: bytes = field(default_factory=lambda: os.urandom(16))  # for the envelope's nonce

    def run_once(self) -> str:
        """One pass. Returns idle, done, retry, needs_human or lost_lease (the triage part's outcome)."""
        now = self.clock()
        if self._escalate(now):  # a failed pass writes no heartbeat: the worker must look stalled
            self.queue.heartbeat(self.worker_id, now)
        job = self.queue.claim(self.worker_id, now, self.lease_s)
        if job is None:
            return self._count("idle")
        text = mark(job.ticket_text, f"job:{job.id}", self.secret) if self.mark_input else job.ticket_text
        outcome = self.triage.classify(text, job.attempts)
        if self.realtime:
            time.sleep(min(outcome.latency_s, self.timeout_s))
        finished = now + min(outcome.latency_s, self.timeout_s)
        if outcome.error is None and outcome.latency_s > self.timeout_s:
            error, retryable = "timeout", True
        elif outcome.error is not None:
            error, retryable = outcome.error, True
        else:
            suggestion, reason = parse_suggestion(outcome.text)
            if suggestion is not None:
                result = {
                    "suggestion": suggestion,
                    "model": self.triage.model,
                    "prompt": self.triage.prompt,
                    "latency_s": outcome.latency_s,
                    "applies_to_task": False,  # a person confirms (D3, ESC-N01)
                }
                if self.summarizer is not None:
                    summary, refused = parse_summary(self.summarizer.summarize(text, job.attempts))
                    if summary is not None:
                        result["summary"] = summary
                    else:
                        result["summary_refused"] = refused
                        self._count("summary_refused")
                ok = self.queue.complete(job.id, self.worker_id, result, finished)
                return self._count("done" if ok else "lost_lease")
            # Unusable output is not retried blindly forever: one retry, then a person.
            error, retryable = reason or "schema", job.attempts < 2
        status = self.queue.fail(job.id, self.worker_id, error, finished, retryable=retryable)
        if status is None:
            return self._count("lost_lease")
        return self._count("retry" if status == "queued" else "needs_human")

    def run(self, max_passes: int | None = None, poll_s: float = 1.0) -> dict[str, int]:
        """Loop until `max_passes` (forever if None), sleeping `poll_s` when idle."""
        passes = 0
        while max_passes is None or passes < max_passes:
            if self.run_once() == "idle" and (max_passes is None or passes + 1 < max_passes):
                time.sleep(poll_s)
            passes += 1
        return dict(self.outcomes)

    def drain(self, max_passes: int = 10_000) -> dict[str, int]:
        """Run passes until the queue has nothing available now (for tests and demos)."""
        for _ in range(max_passes):
            if self.run_once() == "idle":
                break
        return dict(self.outcomes)

    def _escalate(self, now: float) -> bool:
        """Run the evaluation pass, if configured. False if it failed; the pass was then rolled back."""
        if self.escalation is None:
            return True
        try:
            result = self.escalation.run(now)
        except Exception:  # noqa: BLE001 - a failed pass is counted and surfaced, never allowed to stop triage
            LOG.exception("escalation pass failed")
            self._count("escalation_failed")
            return False
        self._count("escalation_pass")
        if result.cannot_evaluate:
            self.outcomes["escalation_cannot_evaluate"] = (self.outcomes.get("escalation_cannot_evaluate", 0)
                                                           + result.cannot_evaluate)
        return True

    def _count(self, outcome: str) -> str:
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        return outcome


def is_stalled(last_pass_at: float | None, now: float, stall_after_s: float = STALL_AFTER_S) -> bool:
    """True if no worker has completed a pass within `stall_after_s` (or ever)."""
    return last_pass_at is None or now - last_pass_at > stall_after_s
