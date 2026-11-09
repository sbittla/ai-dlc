"""Who may do what. Relay has four workspace roles: Owner, Admin, Member, Guest."""

from __future__ import annotations

from .models import Project, User


def can_see_billing(user: User) -> bool:
    """Only the Owner can see the Billing tab."""
    return user.role == "Owner"


def can_manage_members(user: User) -> bool:
    return user.role in ("Owner", "Admin")


def can_view_project(user: User, project: Project) -> bool:
    """Guests see only projects they were explicitly invited to; everyone else sees all."""
    if user.role == "Guest":
        return project.id in user.projects
    return True


def check_single_owner(users: list[User]) -> None:
    """A workspace has exactly one Owner."""
    owners = [u for u in users if u.role == "Owner"]
    if len(owners) != 1:
        raise ValueError(f"expected exactly one Owner, found {len(owners)}")
