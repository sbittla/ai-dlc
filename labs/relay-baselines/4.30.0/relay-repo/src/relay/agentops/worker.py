"""Agent runs as durable queue workers (added in 4.30.0; ADR-049).

A worker process claims one job at a time from `AgentJobQueue`, runs the agent for it on Chapter 10's
runtime (`relay.agents`), and records what happened. Many workers can share one queue; any of them can pick up
a run another one started, because everything a run needs to continue is in the run store, not in a process.

What the worker adds to the runtime:

- **Heartbeats between steps.** After every step the run is checkpointed and the job's lease extended. If the
  lease was lost, the worker stops before its next effect (`LeaseLost`); if a person cancelled the job, the
  run stops as `stopped` with reason `cancelled` (`JobCancelled`). Neither interrupts a step in the middle.
- **Classified failures.** A rate limit, a timeout or a dependency error is retried with backoff and counted
  by the dependency's circuit breaker; a poison payload goes straight to the dead-letter state; a revoked
  agent's job goes there too, because a person decides whether it runs again.
- **Breakers before claims.** A worker does not claim a job whose dependency's breaker is open, so jobs wait in
  the queue instead of spending their attempts on calls that would fail.
- **One trace per job.** A `process_job` span links to the trace that enqueued the job, and the run's tool
  calls are its children, so a request, its queue wait, the agent's steps and the sandbox are one picture.

Approval waits park the job (`waiting`) without spending an attempt; the approval's decision wakes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from ..agents import RunStore, StepRecord, run_loop
from ..agents.state import FINAL
from ..telemetry import semconv
from ..telemetry.trace import CONSUMER, ERROR, INTERNAL, OK, parse_traceparent
from .jobs import AgentJob, AgentJobQueue, JobCancelled, LeaseLost
from .resilience import CircuitBreaker, DependencyError, DependencyTimeout, PoisonPayload, RateLimited

RUN_STATUS_TO_JOB = {"finished": "done", "handed_back": "done", "stopped": "done", "awaiting_approval": "waiting",
                     "delegation_expired": "waiting", "revoked": "dead", "failed": "dead"}


@dataclass(frozen=True)
class Outcome:
    """What a handler reports: the run's status and reason, and the result to store with the job."""

    status: str                   # a run status (relay.agents.state.STATUSES)
    reason: str = ""
    result: dict = field(default_factory=dict)


@dataclass
class JobContext:
    job: AgentJob
    queue: AgentJobQueue
    worker_id: str
    clock: Callable[[], float]
    lease_s: float
    span: object = None           # the job's span, for child spans; None without a tracer
    tracer: object = None

    def checkpoint(self) -> None:
        """Extend the lease between steps. Raises LeaseLost or JobCancelled."""
        self.queue.heartbeat(self.job.id, self.job.lease_token, self.clock(), self.lease_s)


@dataclass(frozen=True)
class AgentKind:
    """How to run one kind of job: the dependency its breaker guards, and the handler."""

    dependency: str
    handler: Callable[[JobContext], Outcome]


@dataclass
class AgentWorker:
    queue: AgentJobQueue
    kinds: dict[str, AgentKind]
    worker_id: str
    clock: Callable[[], float]
    breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    lease_s: float = 120.0
    tracer: object = None
    outcomes: dict[str, int] = field(default_factory=dict)

    def _count(self, outcome: str) -> str:
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        return outcome

    def run_once(self) -> str:
        """Claim and process one job. Returns idle, paused, done, waiting, retry, dead, cancelled or lost_lease."""
        ready, probes = [], []
        for name, kind in self.kinds.items():
            breaker = self.breakers.get(kind.dependency)
            if breaker is None:
                ready.append(name)
                continue
            was = breaker.state
            if breaker.allow():
                ready.append(name)
                if breaker.state == "half_open" or was == "half_open":
                    probes.append(breaker)
        if not ready:
            return self._count("paused")
        job = self.queue.claim(self.worker_id, self.clock(), self.lease_s, tuple(sorted(ready)))
        claimed_dep = self.kinds[job.kind].dependency if job else None
        for breaker in probes:  # a probe slot not used by this claim is given back
            if breaker.dependency != claimed_dep:
                breaker.probing = False
        if job is None:
            return self._count("idle")
        return self._count(self._process(job))

    def _process(self, job: AgentJob) -> str:
        """Run one job. Whatever happens, a half-open breaker's trial slot is released: a trial that ended in a
        poison payload, a cancellation or a lost lease says nothing about the dependency (neutral), and one that
        ended in an unclassified error counts as a failure. Otherwise one bad trial job would leave the breaker
        refusing every claim until the process restarts."""
        breaker = self.breakers.get(self.kinds[job.kind].dependency)
        try:
            return self._run(job, breaker)
        finally:
            if breaker is not None:
                breaker.release()

    def _run(self, job: AgentJob, breaker: CircuitBreaker | None) -> str:
        kind = self.kinds[job.kind]
        span = self._start_span(job)
        ctx = JobContext(job, self.queue, self.worker_id, self.clock, self.lease_s, span, self.tracer)
        now = self.clock
        try:
            out = kind.handler(ctx)
        except JobCancelled:
            return self._end(span, "cancelled")
        except LeaseLost:
            return self._end(span, "lost_lease")
        except RateLimited as exc:
            if breaker:
                breaker.record_failure(exc.retry_after_s)
            return self._end(span, self._fail(job, "rate_limited", now(), True, exc.retry_after_s))
        except (DependencyTimeout, DependencyError) as exc:
            if breaker:
                breaker.record_failure()
            code = "timeout" if isinstance(exc, DependencyTimeout) else "dependency_error"
            return self._end(span, self._fail(job, code, now(), True))
        except PoisonPayload as exc:
            return self._end(span, self._fail(job, f"poison_payload: {exc}", now(), False, dead="poison_payload"))
        except Exception as exc:  # noqa: BLE001 - an unknown failure is retried, then reaches a person
            if breaker:
                breaker.record_failure()
            return self._end(span, self._fail(job, f"error: {type(exc).__name__}", now(), True))
        if breaker:
            breaker.record_success()
        target = RUN_STATUS_TO_JOB.get(out.status, "dead")
        result = {"run_status": out.status, "reason": out.reason, **out.result}
        try:
            if target == "done":
                self.queue.complete(job.id, job.lease_token, result, now())
                return self._end(span, "done", out)
            if target == "waiting":
                self.queue.park(job.id, job.lease_token, out.status, now())
                return self._end(span, "waiting", out)
            self.queue.fail(job.id, job.lease_token, f"{out.status}: {out.reason}"[:200], now(), retryable=False,
                            dead_reason=out.status)
            return self._end(span, "dead", out)
        except LeaseLost:
            return self._end(span, "lost_lease")

    def _fail(self, job: AgentJob, error: str, now: float, retryable: bool, retry_after: float | None = None,
              dead: str | None = None) -> str:
        try:
            status = self.queue.fail(job.id, job.lease_token, error, now, retryable, retry_after, dead)
        except LeaseLost:
            return "lost_lease"
        return "retry" if status == "queued" else "dead"

    def _start_span(self, job: AgentJob):
        if self.tracer is None:
            return None
        links = []
        parent = parse_traceparent(job.traceparent)
        if parent:
            links.append({"trace_id": parent["trace_id"], "span_id": parent["span_id"]})
        return self.tracer.start(f"process_job {job.kind}", CONSUMER, links=links, attributes={
            semconv.GEN_AI_OPERATION_NAME: "invoke_agent", semconv.RELAY_STEP_SEQ: job.attempts})

    def _end(self, span, outcome: str, out: Outcome | None = None) -> str:
        if span is not None:
            span.set(semconv.RELAY_WORKER_OUTCOME, outcome)
            if out is not None:
                span.set(semconv.RELAY_AGENT_STATUS, out.status)
                span.set(semconv.RELAY_AGENT_STOP_REASON, out.reason)
            self.tracer.end(span, OK if outcome in ("done", "waiting") else ERROR)
        return outcome


def _ns(text: str) -> int | None:
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1_000_000_000)
    except ValueError:
        return None


def trace_steps(tracer, parent, run: dict, steps: list[dict]) -> int:
    """Child spans for a run's steps under the job's span (Chapter 16's `execute_tool` shape). Returns the count.

    A step's span runs from its journal time to the next step's (the last ends at the run's update). Only the
    tool, the outcome, the code and the argument hash are recorded, never arguments or results; a sandbox run
    adds an event with its status and the number of refusals. The journal's taint record is not a tool call and
    gets no span.
    """
    if tracer is None or parent is None:
        return 0
    calls = [s for s in steps if s["tool"] != "run.taint"]
    for i, step in enumerate(calls):
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        start = _ns(step["at"])
        end = _ns(calls[i + 1]["at"]) if i + 1 < len(calls) else _ns(run["updated_at"])
        span = tracer.start(f"execute_tool {step['tool']}", INTERNAL, parent=parent, start_ns=start,
                            attributes={semconv.GEN_AI_OPERATION_NAME: "execute_tool",
                                        semconv.GEN_AI_TOOL_NAME: step["tool"], semconv.RELAY_STEP_SEQ: step["seq"],
                                        semconv.RELAY_STEP_OUTCOME: step["outcome"],
                                        semconv.RELAY_ARGS_SHA256: step["args_sha256"],
                                        semconv.RELAY_STEP_CODE: (result or {}).get("code") or "",
                                        semconv.RELAY_AGENT_RUN_ID: run["run_id"]})
        value = (result or {}).get("value")
        if isinstance(value, dict) and "refusals" in value and "status" in value:
            span.add_event("sandbox", span.start_ns, {semconv.RELAY_STEP_OUTCOME: value["status"],
                                                      semconv.RELAY_STEP_SEQ: len(value["refusals"])})
        end_ns = span.start_ns if end is None else max(span.start_ns, end)
        tracer.end(span, ERROR if step["outcome"] in ("error", "refused") else OK, end_ns=end_ns)
    return len(calls)


def run_agent(ctx: JobContext, store: RunStore, build, at: Callable[[], str]) -> Outcome:
    """Start or resume the run for this job and drive it until it ends, pauses or the job is taken away.

    `build(run_id, run)` returns (policy, boundary, rules, done_check), restoring the policy and the meter from
    the run's checkpoint. The run's request key is the job's kind and dedup key, so every delivery of the same
    job, on any worker, maps to one run.
    """
    job = ctx.job
    payload = job.payload
    for name in ("task_id", "agent_id"):
        if not isinstance(payload.get(name), str) or not payload[name]:
            raise PoisonPayload(f"{name} missing")
    run_id, _ = store.start_run(f"{job.kind}:{job.dedup_key}", payload["task_id"], payload.get("design", "routed"),
                                payload["agent_id"], payload.get("on_behalf_of"), at(), payload.get("budget"))
    run = store.run(run_id)
    if run["status"] in FINAL:
        return Outcome(run["status"], run["reason"] or "", {"run_id": run_id, "replayed": True})
    if run["status"] != "running":
        store.set_status(run_id, "running", None, at())
    policy, boundary, rules, done_check = build(run_id, run)
    before = len(store.steps(run_id))  # this attempt's steps are traced under this job's span
    history = [StepRecord(**r) for r in run["checkpoint"].get("history", [])]

    def checkpoint(records: list[StepRecord]) -> None:
        # Heartbeat first: a worker that has lost the job, or whose job was cancelled, stops here without writing
        # the run's checkpoint. The step it just finished was journalled by the boundary, so the lease must be
        # longer than the longest step (the sandbox timeout plus the model timeout) for that write to be fenced.
        ctx.checkpoint()
        store.save_checkpoint(run_id, {"history": [r.__dict__ for r in records], "meter": boundary.meter.snapshot(),
                                       "policy": getattr(policy, "state", lambda: {})()}, at())

    try:
        result = run_loop(policy, boundary, rules, done_check, history, checkpoint)
    except JobCancelled:
        store.set_status(run_id, "stopped", "cancelled", at())
        trace_steps(ctx.tracer, ctx.span, store.run(run_id), store.steps(run_id)[before:])
        raise
    store.save_checkpoint(run_id, {"history": [r.__dict__ for r in result.history],
                                   "meter": boundary.meter.snapshot(),
                                   "policy": getattr(policy, "state", lambda: {})()}, at())
    store.set_status(run_id, result.status, result.reason, at())
    trace_steps(ctx.tracer, ctx.span, store.run(run_id), store.steps(run_id)[before:])
    return Outcome(result.status, result.reason, {"run_id": run_id, "approval_id": result.approval_id,
                                                  "usd": round(boundary.meter.usd, 6)})


def decide_and_wake(gate, queue: AgentJobQueue, approval_id: str, proof: dict, approve: bool, reason: str,
                    now: float):
    """Record a person's decision on a parked run's approval, then wake its job (4.30.0; ADR-049).

    `gate.decide` authenticates the decider and checks the approver rule; only after it accepts the decision is
    the job requeued, so a refused decision wakes nothing. A denial wakes the job too: the run resumes, its call
    is refused as `approval_denied`, and it hands back. The job is found from the run's request key, which
    `run_agent` sets to the job's kind and business key.
    """
    approval = gate.decide(approval_id, proof, approve, reason)
    kind, _, dedup_key = gate.store.run(approval.run_id)["request_key"].partition(":")
    row = queue.conn.execute("SELECT id FROM agent_jobs WHERE kind = ? AND dedup_key = ?", (kind, dedup_key)).fetchone()
    if row is not None:
        queue.wake(row[0], now, approval.decided_by)
    return approval
