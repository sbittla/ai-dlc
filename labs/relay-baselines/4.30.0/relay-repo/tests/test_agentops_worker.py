"""The spec-to-PR helper as a durable queue worker (4.30.0, ADR-049 to ADR-051), under injected faults.

The model is a scripted stand-in (tests/agentops_helpers.py); the runtime, the queue, the ledger, the sandbox,
the shared registry and the boundary are Relay's real code."""

import pytest

from agentops_helpers import REGISTRY, Deployment, SimulatedCrash
from relay.agentops import SharedRegistry
from relay.agentops.resilience import DependencyTimeout
from relay.agentops.worker import decide_and_wake
from relay.audit import AuditTrail, killswitch
from relay.telemetry import MemoryExporter, Tracer
from relay.telemetry.trace import IdSource

RUN = "run-spec-to-pr:RLY-2301"


def finish(d, worker):
    """Run until the job waits for approval, approve as the requester (which wakes it), and run it to the end."""
    job = d.queue.get(1)
    assert worker.run_once() == "waiting"
    assert d.approve_pending() == 1
    assert d.queue.get(job.id).status == "queued"
    return worker.run_once()


def test_the_helper_runs_as_a_job_waits_for_approval_without_spending_an_attempt_and_finishes(tmp_path):
    d = Deployment(tmp_path)
    d.enqueue()
    assert finish(d, d.worker()) == "done"
    job = d.queue.get(1)
    assert (job.status, job.attempts, job.result["run_status"]) == ("done", 1, "finished")
    assert d.github.creates == 1 and [r.status for r in d.sandbox_runs] == ["ok"]


def test_a_duplicate_delivery_is_the_same_job_and_the_same_run(tmp_path):
    d = Deployment(tmp_path)
    first, _ = d.enqueue()
    again, created = d.enqueue()
    assert not created and again.id == first.id
    assert finish(d, d.worker()) == "done"
    runs = d.store.conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    assert runs == 1 and d.github.creates == 1


def test_a_worker_that_dies_after_the_code_host_created_the_pull_request_is_replaced_without_a_second_one(tmp_path):
    d = Deployment(tmp_path)
    d.enqueue()
    w1 = d.worker("w1")
    assert w1.run_once() == "waiting"
    d.approve_pending()
    d.github.crash_after_create = True
    with pytest.raises(SimulatedCrash):
        w1.run_once()
    d.clock.t += 121  # the dead worker's lease expires
    d2 = Deployment(tmp_path, d.clock)  # a new process: every object rebuilt from the shared files
    assert d2.worker("w2").run_once() == "done"
    assert d2.github.creates == 1 and d2.queue.get(1).attempts == 2
    assert d2.ledger.get("pr:RLY-2301")["attempts"] == 2  # repeated once, deduplicated by the code host's key


def test_a_rate_limited_provider_opens_the_breaker_and_jobs_wait_instead_of_burning_attempts(tmp_path):
    d = Deployment(tmp_path)
    for n in (1, 2, 3, 4):
        d.enqueue(f"RLY-230{n}")
    d.rate_limit_until = d.clock.t + 100
    w = d.worker()
    assert [w.run_once() for _ in range(4)] == ["retry", "retry", "retry", "paused"]
    assert d.breaker.state == "open" and d.queue.get(4).attempts == 0
    d.clock.t += 121
    outcomes = [w.run_once() for _ in range(4)]
    assert outcomes == ["waiting"] * 4 and d.breaker.state == "closed"
    # each rate-limited call spent one attempt; the fourth job, held back by the breaker, spent none
    assert [d.queue.get(n).attempts for n in (1, 2, 3, 4)] == [1, 1, 1, 0]


def test_a_dependency_that_always_times_out_ends_in_the_dead_letter_state(tmp_path):
    d = Deployment(tmp_path)
    job, _ = d.queue.enqueue("spec-to-pr", "RLY-9", {"task_id": "RLY-9", "agent_id": "spec-to-pr-helper",
                                                      "on_behalf_of": "priya.n"}, d.clock(), max_attempts=3)
    w = d.worker()
    original = d.build

    def timing_out(run_id, run):
        policy, *rest = original(run_id, run)
        policy.model_error = DependencyTimeout("model", 30)
        return (policy, *rest)
    d.build = timing_out
    d.breaker.threshold = 99
    outcomes = []
    for _ in range(3):
        outcomes.append(w.run_once())
        d.clock.t = d.queue.get(job.id).available_at
    assert outcomes == ["retry", "retry", "dead"]
    assert d.queue.get(job.id).dead_reason == "attempts_exhausted"


def test_a_poison_payload_is_dead_lettered_on_its_first_attempt(tmp_path):
    d = Deployment(tmp_path)
    d.queue.enqueue("spec-to-pr", "RLY-0", {"agent_id": "spec-to-pr-helper"}, d.clock())
    assert d.worker().run_once() == "dead"
    job = d.queue.get(1)
    assert (job.dead_reason, job.attempts) == ("poison_payload", 1)


def test_a_person_cancels_a_running_job_and_it_stops_between_steps(tmp_path):
    d = Deployment(tmp_path)
    d.enqueue()
    d.on_sandbox = lambda result: d.queue.cancel(1, "priya.n", d.clock())  # cancelled while tests run
    assert d.worker().run_once() == "cancelled"
    assert d.queue.get(1).status == "cancelled" and d.store.run(RUN)["reason"] == "cancelled"
    assert d.github.creates == 0


def test_a_kill_switch_tripped_elsewhere_stops_the_run_and_dead_letters_the_job(tmp_path):
    d = Deployment(tmp_path)
    d.enqueue()
    monitor = SharedRegistry(REGISTRY, str(tmp_path / "relay.db"))  # another process: the monitor
    d.on_sandbox = lambda result: killswitch.trip(monitor, AuditTrail(), "spec-to-pr-helper",
                                                           "detection:DR-003", "drill")
    assert d.worker().run_once() == "dead"
    job = d.queue.get(1)
    assert job.dead_reason == "revoked" and d.store.run(RUN)["status"] == "revoked" and d.github.creates == 0
    refused = [r for r in d.trail.records if r["outcome"] == "refused"]
    assert refused and refused[-1]["detail"]["code"] == "revoked:disabled"


def test_agent_code_that_tries_to_escape_is_refused_and_the_run_hands_back(tmp_path):
    d = Deployment(tmp_path, code="import os\nos.system('curl http://169.254.169.254/')\n"
                                  "def add(a, b):\n    return a + b\n")
    d.enqueue()
    assert d.worker().run_once() == "done"
    assert d.store.run(RUN)["status"] == "handed_back" and d.github.creates == 0
    assert [r["reason"] for r in d.sandbox_runs[0].refusals] == ["refused:process"]
    steps = [s for s in d.store.steps(RUN) if s["tool"] == "run_tests"]
    assert steps[0]["result"]["value"]["refusals"] == ["refused:process"]


def test_one_trace_per_job_attempt_links_to_the_request_and_holds_the_tool_calls(tmp_path):
    exporter = MemoryExporter()
    tracer = Tracer(exporter, IdSource(seed=18))
    d = Deployment(tmp_path)
    request = tracer.start("POST /v1/spec-to-pr")
    tracer.end(request)
    parent = f"00-{request.trace_id}-{request.span_id}-01"
    d.enqueue(traceparent=parent)
    assert finish(d, d.worker(tracer=tracer)) == "done"
    jobs = [s for s in exporter.spans if s.name == "process_job spec-to-pr"]
    tools = [s for s in exporter.spans if s.name.startswith("execute_tool")]
    assert len(jobs) == 2 and all(j.links[0]["span_id"] == request.span_id for j in jobs)
    assert {t.parent_span_id for t in tools} <= {j.span_id for j in jobs}
    assert [t.name for t in tools if t.parent_span_id == jobs[1].span_id][-1] == "execute_tool open_pull_request"
    assert any(e["name"] == "sandbox" for t in tools for e in t.events)


def test_a_refused_decision_wakes_nothing(tmp_path):
    d = Deployment(tmp_path)
    d.enqueue()
    assert d.worker().run_once() == "waiting"
    approval_id = d.store.conn.execute("SELECT approval_id FROM agent_approvals").fetchone()[0]
    with pytest.raises(Exception):
        decide_and_wake(d.gate, d.queue, approval_id, d.person("sam.o"), True, "not the requester", d.clock())
    assert d.queue.get(1).status == "waiting"


def test_a_worker_whose_step_outlasted_its_lease_stops_without_overwriting_the_run(tmp_path):
    """The lease must exceed the longest step. Here a step outlasts it: another worker takes the job, and the
    first learns it lost the job at its next heartbeat, before writing the run's checkpoint."""
    d = Deployment(tmp_path)
    d.enqueue()
    other = Deployment(tmp_path, d.clock)
    taken = []

    def slow_step(result):
        d.clock.t += 200  # longer than the 120-second lease
        taken.append(other.worker("w2").run_once())
    d.on_sandbox = slow_step
    assert d.worker("w1").run_once() == "lost_lease"
    assert taken == ["waiting"] and d.queue.get(1).status == "waiting" and d.queue.get(1).lease_token == 2
    assert d.store.run(RUN)["checkpoint"]["policy"]["position"] == 4  # the second worker's checkpoint stands
