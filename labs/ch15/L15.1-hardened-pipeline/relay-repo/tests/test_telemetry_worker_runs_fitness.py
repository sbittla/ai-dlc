"""The worker observed from outside, agent runs traced from their journal, and runtime fitness checks
(4.27.0, ADR-036, ADR-037). The escalation fixtures follow tests/test_worker_escalation.py: 02:30 UTC on
Tuesday 24 November 2026, a P1 rule with steps at 10 and 20 minutes."""

import json
from datetime import datetime, timedelta, timezone

from relay.agents.state import RunStore
from relay.escalation import EngineConfig, EscalationStore, Rule, Step, save_rule, set_priority
from relay.models import Project, Task, User
from relay.store import TaskStore
from relay.telemetry import IdSource, Logger, MemoryExporter, Meter, Tracer
from relay.telemetry.fitness import (cardinality_check, escalation_step_delays, heartbeat_check, step_delay_check,
                                     telemetry_leak_check)
from relay.telemetry.otlp import FileExporter
from relay.telemetry.runs import run_signals, trace_run
from relay.telemetry.worker import WorkerTelemetry
from relay.worker import EscalationPasses, TriageQueue, Worker
from relay.worker.triage import SimulatedTriage

T0 = datetime(2026, 11, 24, 2, 30, tzinfo=timezone.utc)
ROTTERDAM = Project(10, "Rotterdam")
ADMIN = User(2, "joost@customer.example", "Joost", "Admin", "Europe/Berlin")
MEMBER = User(4, "daan@customer.example", "Daan", "Member", "Europe/Berlin")
USERS = {u.id: u for u in (ADMIN, MEMBER)}
TASK = Task(7, 10, "Scanner gateway down in hall 3")
RULE = Rule("R-ROT-P1", 10, "P1", (Step(1, 10, (4,)), Step(2, 20, (2,))))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def telemetry():
    exp = MemoryExporter()
    return WorkerTelemetry(Tracer(exp, IdSource(seed=2)), Meter(), Logger(exp)), exp


def escalation_worker(broken=False):
    store, tasks, queue = EscalationStore(), TaskStore(), TriageQueue()
    tasks.add(TASK)
    save_rule(store, RULE, ADMIN, ROTTERDAM, USERS, T0 - timedelta(hours=1))
    set_priority(store, TASK, ROTTERDAM, MEMBER, "P1", T0)
    passes = EscalationPasses(store, tasks, {10: ROTTERDAM}, EngineConfig("https://relay.example/ws-demo"))
    if broken:
        store.conn.execute("DROP TABLE esc_fired")
    clock = Clock((T0 + timedelta(minutes=10)).timestamp())
    return Worker(queue, SimulatedTriage(), clock=clock, escalation=passes), store, tasks, queue, clock


def test_a_failing_pass_is_an_error_span_and_writes_no_heartbeat_so_the_stall_alert_fires():
    worker, _, _, queue, clock = escalation_worker(broken=True)
    tel, exp = telemetry()
    assert tel.observe(worker) == "idle"
    span, = exp.spans
    assert span.status == "ERROR" and span.attributes["relay.escalation.result"] == "failed"
    assert exp.logs[0].severity_text == "ERROR"
    assert tel.escalations.points() == [({"relay.escalation.result": "failed"}, 1)]
    assert tel.heartbeat(queue, clock()) is None  # no pass ever completed: RF-002 fails
    assert not heartbeat_check(None).passed


def test_a_healthy_pass_records_ok_and_a_fresh_heartbeat():
    worker, _, _, queue, clock = escalation_worker()
    tel, exp = telemetry()
    tel.observe(worker)
    clock.t += 301
    age = tel.heartbeat(queue, clock())
    assert age == 301.0 and not heartbeat_check(age).passed and heartbeat_check(300.0).passed
    assert tel.age.points() == [({}, 301.0)]


def test_rf001_runtime_check_for_esc_ac30_step_delays_from_the_escalation_store():
    """ESC-AC30 is outside ESC-SPEC-1 1.2.0, a runtime check; this tests RF-001, which implements it."""
    worker, store, tasks, _, clock = escalation_worker()
    worker.run_once()                     # 02:40: step 1 due at 02:40, fired at 02:40
    clock.t += 21 * 60 + 30               # 03:01:30: step 2 was due at 02:50, fired 11.5 minutes late
    worker.run_once()
    delays = escalation_step_delays(store, tasks, [7], T0, T0 + timedelta(days=7))
    assert delays == [0.0, 690.0]
    check = step_delay_check(delays)
    assert (check.passed, check.value) == (False, 0.5)
    assert step_delay_check([0.0] * 19 + [61.0]).passed  # 19 of 20 is exactly 95%
    assert not step_delay_check([0.0] * 18 + [61.0] * 2).passed


def journal():
    store = RunStore()
    run_id, _ = store.start_run("k1", "RLY-2301", "routed", "spec-to-pr-helper", "priya.n", "2027-02-10T10:00:00Z")
    seq, _ = store.begin_step(run_id, "idem-1", "spec-to-pr-helper", "edit_file", "a" * 64, "2027-02-10T10:00:05Z")
    store.finish_step(run_id, seq, "ok", {"value": "done"})
    store.note_step(run_id, "spec-to-pr-helper", "open_pull_request", "b" * 64, "refused",
                    {"code": "unknown_outcome", "detail": "a person checks"}, "2027-02-10T10:00:09Z")
    store.set_status(run_id, "stopped", "budget:usd", "2027-02-10T10:00:12Z")
    return store, run_id


def test_an_agent_run_becomes_a_trace_without_the_person_or_the_arguments():
    store, run_id = journal()
    exp = MemoryExporter()
    tracer, meter = Tracer(exp, IdSource(seed=4)), Meter()
    root = trace_run(tracer, meter, store.run(run_id), store.steps(run_id))
    assert root.name == "invoke_agent spec-to-pr-helper" and root.status == "ERROR"
    assert root.attributes["relay.agent.stop_reason"] == "budget:usd"
    assert "on_behalf_of" not in json.dumps([s.attributes for s in exp.spans])
    assert "priya.n" not in json.dumps([s.attributes for s in exp.spans])
    tools = [(s.attributes["gen_ai.tool.name"], s.attributes["relay.step.outcome"], s.duration_s)
             for s in exp.spans if s.parent_span_id]
    assert tools == [("edit_file", "ok", 4.0), ("open_pull_request", "refused", 3.0)]
    assert meter.instruments["relay.agent.runs"].points() == [
        ({"gen_ai.agent.id": "spec-to-pr-helper", "relay.agent.status": "budget"}, 1)]


def test_run_signals_feed_al004_and_al005():
    store, run_id = journal()
    signals = run_signals([store.run(run_id)], {run_id: store.steps(run_id)})
    assert signals == {"relay.agent.budget_stops": {"spec-to-pr-helper": 1},
                       "relay.agent.unknown_outcome": {"spec-to-pr-helper": 1}}


def test_rf003_finds_nothing_in_clean_exports_and_finds_a_leak_in_a_dirty_one(tmp_path):
    exp = FileExporter(tmp_path / "clean", "relay-service", "nonprod")
    tracer = Tracer(exp, IdSource(seed=5))
    tracer.end(tracer.start("GET", attributes={"http.route": "/v1/x", "enduser.email": "jane.doe@example.com"}))
    exp.flush()
    assert telemetry_leak_check([tmp_path / "clean" / "traces.jsonl"]).passed
    dirty = tmp_path / "dirty.jsonl"  # what an unfiltered exporter would have written
    dirty.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [{"attributes": [
        {"key": "gen_ai.input.messages", "value": {"stringValue": "call me on 030 1234567"}}]}]}]}]}) + "\n")
    check = telemetry_leak_check([dirty])
    assert not check.passed and check.value == 2 and "gen_ai.input.messages" in check.detail


def test_rf004_cardinality():
    m = Meter()
    assert cardinality_check(m).passed
    c = m.counter("x", limit=1)
    c.add(1, {"http.route": "/a"})
    c.add(1, {"http.route": "/b"})
    assert not cardinality_check(m).passed


def test_al006_counts_a_held_p1_until_its_task_is_acknowledged():
    from relay.escalation import acknowledge, run_pass
    from relay.telemetry.fitness import held_p1_unacknowledged
    store, tasks = EscalationStore(), TaskStore()
    rule = Rule("R-ROT-P1", 10, "P1", (Step(1, 10, (4,)),))
    save_rule(store, rule, ADMIN, ROTTERDAM, USERS, T0 - timedelta(hours=1))
    for i in range(21):  # 21 P1 tasks for one target: the cap of 20 holds the last email
        task = Task(100 + i, 10, f"Outage symptom {i}")
        tasks.add(task)
        set_priority(store, task, ROTTERDAM, MEMBER, "P1", T0)
    from relay.worker.escalation import TaskLookup
    run_pass(store, TaskLookup(tasks), {10: ROTTERDAM}, EngineConfig("https://relay.example/ws-demo"),
             T0 + timedelta(minutes=10))
    ids = list(range(100, 121))
    assert held_p1_unacknowledged(store, ids, T0 + timedelta(minutes=15)) == 0  # held 5 minutes ago
    assert held_p1_unacknowledged(store, ids, T0 + timedelta(minutes=21)) == 1
    held_task = next(t for t in ids if any(a["kind"] == "not_emailed" for a in store.activity(t)))
    acknowledge(store, tasks.get(held_task), ROTTERDAM, MEMBER, T0 + timedelta(minutes=12))
    assert held_p1_unacknowledged(store, ids, T0 + timedelta(minutes=21)) == 0
