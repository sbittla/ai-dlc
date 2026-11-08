"""The JSON views Relay's web client renders."""

from __future__ import annotations

from .duedates import display_due_date
from .models import Project, Task, User
from .roles import can_view_project


def task_view(task: Task, project: Project, viewer: User) -> dict:
    """The task as `viewer` sees it. PermissionError if they may not see the project."""
    if task.project_id != project.id:
        raise ValueError("task does not belong to project")
    if not can_view_project(viewer, project):
        raise PermissionError(f"user {viewer.id} cannot view project {project.id}")
    return {
        "id": task.id,
        "project": project.name,
        "title": task.title,
        "status": task.status,
        "due_date": display_due_date(task.due, viewer.tz).isoformat() if task.due else None,
    }
