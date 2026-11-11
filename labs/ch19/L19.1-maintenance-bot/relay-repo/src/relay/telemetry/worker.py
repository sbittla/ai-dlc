"""Telemetry for the background worker, observed from outside it (added in 4.27.0; ADR-036).

`relay.worker` stays unchanged: it already counts its outcomes in `Worker.outcomes` and writes a heartbeat
after every pass whose escalation part succeeded. `WorkerTelemetry.observe` wraps one `run_once` call,
turns the change in those counts into a span and metrics, and `heartbeat` reads the age of the newest
heartbeat from the queue. Chapter 9 and Chapter 8 asked for two alerts from these signals:

- AL-001: no completed pass for 5 minutes (`relay.worker.heartbeat_age` over 300 s), which is ESC-AC29's
  page. A pass whose escalation part fails writes no heartbeat, so failing passes page through this rule.
- AL-002: `relay.escalation.cannot_evaluate` above zero in an hour: a rule that cannot be timed was
  skipped, and every other rule still fired.

This module never imports `relay.worker`; it uses the worker object it is given (AR3, ADR-036).
"""

from __future__ import annotations

from . import semconv
from .trace import ERROR, OK

PASS_KEYS = ("escalation_pass", "escalation_failed", "escalation_cannot_evaluate")


class WorkerTelemetry:
    def __init__(self, tracer, meter, logger) -> None:
        self.tracer, self.meter, self.logger = tracer, meter, logger
        self.passes = meter.counter("relay.worker.passes", "{pass}", "worker passes by triage outcome", limit=20)
        self.escalations = meter.counter("relay.escalation.passes", "{pass}", "escalation passes by result", limit=5)
        self.cannot = meter.counter("relay.escalation.cannot_evaluate", "{rule}",
                                    "task-rule pairs skipped because their timing could not be computed", limit=2)
        self.age = meter.gauge("relay.worker.heartbeat_age", "s", "seconds since the newest completed pass", limit=2)

    def observe(self, worker) -> str:
        before = {k: worker.outcomes.get(k, 0) for k in PASS_KEYS}
        span = self.tracer.start("worker.pass")
        outcome = worker.run_once()
        delta = {k: worker.outcomes.get(k, 0) - before[k] for k in PASS_KEYS}
        span.set(semconv.RELAY_WORKER_OUTCOME, outcome)
        self.passes.add(1, {semconv.RELAY_WORKER_OUTCOME: outcome})
        if delta["escalation_failed"]:
            span.set(semconv.RELAY_ESCALATION_RESULT, "failed")
            self.escalations.add(delta["escalation_failed"], {semconv.RELAY_ESCALATION_RESULT: "failed"})
            self.logger.emit("ERROR", "escalation pass failed; no heartbeat written", span=span)
        elif delta["escalation_pass"]:
            span.set(semconv.RELAY_ESCALATION_RESULT, "ok")
            self.escalations.add(delta["escalation_pass"], {semconv.RELAY_ESCALATION_RESULT: "ok"})
        if delta["escalation_cannot_evaluate"]:
            self.cannot.add(delta["escalation_cannot_evaluate"])
            self.logger.emit("WARN", f"{delta['escalation_cannot_evaluate']} rule(s) could not be evaluated",
                             span=span)
        self.tracer.end(span, ERROR if delta["escalation_failed"] else OK)
        return outcome

    def heartbeat(self, queue, now: float) -> float | None:
        last = queue.last_pass_at()
        age = None if last is None else round(now - last, 1)
        if age is not None:
            self.age.set(age)
        return age
