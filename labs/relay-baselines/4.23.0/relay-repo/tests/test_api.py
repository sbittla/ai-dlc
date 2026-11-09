from datetime import date

import pytest

from relay.api import task_view
from relay.models import Project, Task, User

PROJECT = Project(10, "Launch")
TASK = Task(7, 10, "Publish pricing page", due=date(2026, 11, 20))


def test_task_view_has_the_fields_the_client_renders():
    viewer = User(3, "cy@example.com", "Cy", "Member", "Europe/Berlin")
    assert task_view(TASK, PROJECT, viewer) == {
        "id": 7, "project": "Launch", "title": "Publish pricing page",
        "status": "open", "due_date": "2026-11-20",
    }


def test_guest_cannot_view_a_project_they_were_not_invited_to():
    guest = User(4, "dee@example.com", "Dee", "Guest", "UTC", frozenset({11}))
    with pytest.raises(PermissionError):
        task_view(TASK, PROJECT, guest)
