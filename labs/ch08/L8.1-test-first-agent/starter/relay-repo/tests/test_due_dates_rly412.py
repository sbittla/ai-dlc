"""RLY-412: due dates displayed one day early for viewers more than 12 hours ahead of UTC.

Written before the fix, and seen to fail on the unfixed code (5 failures).
"""

from datetime import date

import pytest

from relay.api import task_view
from relay.duedates import display_due_date
from relay.models import Project, Task, User
from relay.timezones import OFFSETS

DUE = date(2026, 11, 20)


@pytest.mark.parametrize("zone", sorted(OFFSETS))
def test_every_viewer_sees_the_stored_due_date(zone):
    assert display_due_date(DUE, zone) == DUE


def test_auckland_viewer_sees_the_stored_date_in_the_task_view():
    viewer = User(5, "mere@example.com", "Mere", "Member", "Pacific/Auckland")
    task = Task(7, 10, "Publish pricing page", due=DUE)
    assert task_view(task, Project(10, "Launch"), viewer)["due_date"] == "2026-11-20"
