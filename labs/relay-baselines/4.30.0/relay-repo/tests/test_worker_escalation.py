"""The worker runs the escalation pass on every loop (4.22.0, ADR-017; spec 1.2.0, B5). Task T25.

Spec: ESC-SPEC-1
Spec version: 1.2.0

The clock is 02:30 UTC on Tuesday 24 November 2026 plus whole minutes, as in
the escalation fixtures. Expected values come from ESC-AC08 and ESC-AC11.
"""

import json
from datetime import datetime, timezone

import pytest

from relay.escalation import EngineConfig, EscalationStore, Rule, Step, acknowledge, save_rule, set_priority
from relay.models import Project, Task, User
from relay.store import TaskStore
from relay.worker import EscalationPasses, TriageQueue, Worker, is_stalled
from relay.worker.__main__ import main
from relay.worker.triage import SimulatedTriage

T0 = datetime(2026, 11, 24, 2, 30, tzinfo=timezone.utc).timestamp()
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


def worker_at(minutes_after_t0: float, broken=False):
    escalation, tasks, queue = EscalationStore(), TaskStore(), TriageQueue()
    tasks.add(TASK)
    save_rule(escalation, RULE, ADMIN, ROTTERDAM, USERS, datetime.fromtimestamp(T0 - 3600, tz=timezone.utc))
    set_priority(escalation, TASK, ROTTERDAM, MEMBER, "P1", datetime.fromtimestamp(T0, tz=timezone.utc))
    passes = EscalationPasses(escalation, tasks, {10: ROTTERDAM}, EngineConfig("https://relay.example/ws-demo"))
    if broken:
        escalation.conn.execute("DROP TABLE esc_fired")  # the pass will fail inside its transaction
    clock = Clock(T0 + 60 * minutes_after_t0)
    return Worker(queue, SimulatedTriage(), clock=clock, escalation=passes), escalation, queue, clock


def emails(store):
    return [json.loads(i.body)["to_user"] for i in store.outbox() if i.kind == "escalation"]


def test_ESC_AC08_a_worker_pass_at_10_minutes_notifies_only_the_first_steps_target():
    worker, store, _, _ = worker_at(10)
    assert worker.run_once() == "idle"
    assert emails(store) == [4]
    assert worker.outcomes == {"escalation_pass": 1, "idle": 1}


def test_a_worker_pass_a_moment_before_10_minutes_sends_nothing():
    worker, store, _, _ = worker_at(9.99)
    worker.run_once()
    assert store.outbox() == []


def test_ESC_AC11_acknowledging_after_step_1_stops_step_2_in_the_next_worker_pass():
    worker, store, _, clock = worker_at(10)
    worker.run_once()
    acknowledge(store, TASK, ROTTERDAM, MEMBER, datetime.fromtimestamp(T0 + 720, tz=timezone.utc))
    clock.t = T0 + 25 * 60
    worker.run_once()
    assert emails(store) == [4]


def test_a_failed_pass_is_counted_and_writes_no_heartbeat_so_the_worker_looks_stalled():
    worker, _, queue, clock = worker_at(10, broken=True)
    assert worker.run_once() == "idle"  # triage still runs
    assert worker.outcomes == {"escalation_failed": 1, "idle": 1}
    assert queue.last_pass_at() is None and is_stalled(queue.last_pass_at(), clock.t)


def test_a_worker_without_escalation_behaves_as_before():
    queue = TriageQueue()
    worker = Worker(queue, SimulatedTriage(), clock=Clock(T0))
    assert worker.run_once() == "idle" and worker.outcomes == {"idle": 1}
    assert queue.last_pass_at() == T0


def test_the_command_needs_a_link_base_with_a_directory(tmp_path):
    directory = tmp_path / "users.json"
    directory.write_text(json.dumps({"projects": [{"id": 10, "name": "Rotterdam"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "relay.db"), "--directory", str(directory), "--drain"])


def test_a_rule_that_cannot_be_timed_is_counted_and_the_pass_still_succeeds():
    """A P2 set at 21:00 Berlin on Friday 31 December 2027 runs into 2028, past the zone table (ADR-010).

    The pass records it as cannot_evaluate and succeeds, so the heartbeat is written: the evaluator works,
    and one rule needs a person. The count reaches the worker's outcomes for Chapter 16 to alert on.
    """
    from relay.escalation import BusinessHours

    p2 = Rule("R-ROT-P2", 10, "P2", (Step(1, 240, (2,)),), "Rotterdam P2",
              BusinessHours("06:00", "22:00", "Europe/Berlin", (1, 2, 3, 4, 5)))
    escalation, tasks, queue = EscalationStore(), TaskStore(), TriageQueue()
    tasks.add(TASK)
    set_at = datetime(2027, 12, 31, 20, 0, tzinfo=timezone.utc)
    save_rule(escalation, p2, ADMIN, ROTTERDAM, USERS, set_at)
    set_priority(escalation, TASK, ROTTERDAM, MEMBER, "P2", set_at)
    passes = EscalationPasses(escalation, tasks, {10: ROTTERDAM}, EngineConfig("https://relay.example/ws-demo"))
    worker = Worker(queue, SimulatedTriage(), clock=Clock(set_at.timestamp() + 3600), escalation=passes)
    worker.run_once()
    assert worker.outcomes == {"escalation_pass": 1, "escalation_cannot_evaluate": 1, "idle": 1}
    assert queue.last_pass_at() == set_at.timestamp() + 3600
