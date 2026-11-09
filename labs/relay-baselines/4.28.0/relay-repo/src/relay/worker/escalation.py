"""The escalation evaluation pass, run by the worker on every loop (added in 4.22.0; ADR-017).

Spec ESC-SPEC-1 1.2.0, B5: `run_pass` evaluates every live rule for every task
with a person-set priority. Until 4.22.0 nothing called it outside tests, so no
step fired in a running Relay. The worker now calls it before it looks for a
triage job, so a pass happens at least once per poll interval (1 s by default).

The worker uses the engine only through `relay.escalation`'s public interface
(AR7). It reads tasks through `relay.store` and is given the workspace's
projects; it never imports `relay.service` (AR3).

Two workers may run passes against the same database. That is safe: each pass
is one BEGIN IMMEDIATE transaction, a step is recorded at most once (D9), and
outbox rows have unique dedupe keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from ..escalation import EngineConfig, EscalationStore, PassResult, run_pass
from ..models import Project, Task
from ..store import TaskStore


class TaskLookup:
    """The part of a Mapping that `run_pass` uses, over the task store: `get(task_id)`, or None."""

    def __init__(self, tasks: TaskStore) -> None:
        self.tasks = tasks

    def get(self, task_id: int, default: Task | None = None) -> Task | None:
        try:
            return self.tasks.get(task_id)
        except KeyError:
            return default


@dataclass
class EscalationPasses:
    """Runs one evaluation pass at the worker's clock time, in UTC."""

    store: EscalationStore
    tasks: TaskStore
    projects: Mapping[int, Project]
    config: EngineConfig

    def run(self, now: float) -> PassResult:
        at = datetime.fromtimestamp(now, tz=timezone.utc)
        return run_pass(self.store, TaskLookup(self.tasks), self.projects, self.config, at)
