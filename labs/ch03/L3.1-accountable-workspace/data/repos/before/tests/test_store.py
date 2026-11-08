from datetime import date

import pytest

from relay.models import Task
from relay.store import TaskStore


def test_add_and_get_round_trips_a_task():
    store = TaskStore()
    store.add(Task(1, 10, "Write release notes", due=date(2026, 11, 20), assignee_id=3))
    assert store.get(1) == Task(1, 10, "Write release notes", "open", date(2026, 11, 20), 3)


def test_task_without_due_date_round_trips_as_none():
    store = TaskStore()
    store.add(Task(2, 10, "Someday"))
    assert store.get(2).due is None


def test_by_project_returns_only_that_project_in_id_order():
    store = TaskStore()
    for tid, pid in [(3, 11), (1, 10), (2, 10)]:
        store.add(Task(tid, pid, f"t{tid}"))
    assert [t.id for t in store.by_project(10)] == [1, 2]
    with pytest.raises(KeyError):
        store.get(99)
