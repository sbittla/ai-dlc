import pytest

from relay import roles
from relay.models import Project, User

OWNER = User(1, "owner@example.com", "Ana", "Owner", "UTC")
ADMIN = User(2, "admin@example.com", "Ben", "Admin", "UTC")
GUEST = User(4, "guest@example.com", "Dee", "Guest", "UTC", frozenset({10}))


def test_only_the_owner_sees_billing():
    assert roles.can_see_billing(OWNER)
    assert not roles.can_see_billing(ADMIN)


def test_admins_manage_members_and_guests_do_not():
    assert roles.can_manage_members(ADMIN)
    assert not roles.can_manage_members(GUEST)


def test_guests_see_only_invited_projects():
    assert roles.can_view_project(GUEST, Project(10, "Launch"))
    assert not roles.can_view_project(GUEST, Project(11, "Payroll"))


def test_a_workspace_has_exactly_one_owner():
    roles.check_single_owner([OWNER, ADMIN])
    with pytest.raises(ValueError):
        roles.check_single_owner([ADMIN, GUEST])
    with pytest.raises(ValueError):
        User(9, "x@example.com", "X", "Superuser", "UTC")
