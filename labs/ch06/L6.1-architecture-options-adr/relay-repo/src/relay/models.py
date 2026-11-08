"""Relay's domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ROLES = ("Owner", "Admin", "Member", "Guest")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: str  # one of ROLES
    tz: str  # an entry in relay.timezones.OFFSETS
    projects: frozenset[int] = field(default_factory=frozenset)  # explicit invitations (Guests)

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown role {self.role!r}")


@dataclass(frozen=True)
class Project:
    id: int
    name: str


@dataclass(frozen=True)
class Task:
    id: int
    project_id: int
    title: str
    status: str = "open"  # open | done
    due: date | None = None  # a calendar date with no time; never an instant
    assignee_id: int | None = None
