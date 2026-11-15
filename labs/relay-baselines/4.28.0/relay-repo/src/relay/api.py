"""The JSON views Relay's web client renders.

From 4.26.0 (ADR-032) text that Relay did not write reaches the client only as HTML from `relay.render`:
the triage summary a model wrote, and the ticket text it was written from. The client shows that HTML as
it is and never runs a Markdown renderer over it.
"""

from __future__ import annotations

from .duedates import display_due_date
from .models import Project, Task, User
from .render import render_text
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


def suggestion_view(result: dict, viewer: User, link_base: str) -> dict:
    """A triage job's result as support staff see it. PermissionError for a Guest.

    The suggestion's fields come from fixed lists, so they are shown as they are. The summary, if the
    worker kept one, is model-written text about customer-written text, so it is rendered by
    `render_text`: no images, and no clickable address outside Relay. `notice` tells the reader what
    was not shown, so a removed image is visible as a removal rather than silently missing.
    """
    if viewer.role == "Guest":
        raise PermissionError(f"user {viewer.id} cannot view triage suggestions")
    suggestion = result["suggestion"]
    view = {key: suggestion[key] for key in ("category", "priority", "team", "confidence")}
    view["applies_to_task"] = False
    summary = result.get("summary")
    if summary is None:
        view["summary_html"], view["notice"] = None, result.get("summary_refused")
        return view
    rendered = render_text(summary, link_base)
    view["summary_html"] = rendered.html
    notes = []
    if rendered.images_removed:
        notes.append(f"{len(rendered.images_removed)} image(s) not shown")
    if rendered.external:
        notes.append(f"{len(rendered.external)} address(es) outside Relay shown as text")
    if rendered.hidden_removed:
        notes.append(f"{rendered.hidden_removed} hidden character(s) removed")
    view["notice"] = "; ".join(notes) or None
    return view
