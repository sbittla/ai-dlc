"""The allowlist: every query an agent may run, and the limits around it (provided).

There is no free-form SQL anywhere in this server. An agent chooses one of
these templates by name and supplies typed parameters; the SQL text is fixed
here, reviewed like any code, and bound with SQLite's parameter binding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_REQUEST_BYTES = 2048   # the whole request, as UTF-8 JSON
DEFAULT_LIMIT = 20         # rows returned when the request gives no limit
MAX_LIMIT = 50             # the most rows one call may return

ALLOWED_TABLES = frozenset({"tasks", "projects", "users", "webhook_deliveries"})
SECRET_COLUMNS = frozenset({"password_hash", "api_token_hash"})  # never selectable, by any template
PII_COLUMNS = {"email": "[redacted:email]", "display_name": "[redacted:name]"}  # returned only redacted


@dataclass(frozen=True)
class Param:
    type: str                    # "int" | "str" | "date" | "enum"
    required: bool = True
    min: int | None = None       # int only, inclusive
    max: int | None = None       # int only, inclusive
    max_len: int | None = None   # str only
    choices: tuple[str, ...] = ()  # enum only
    like: bool = False           # str only: bound as a LIKE pattern '%<escaped>%'


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    sql: str                     # named parameters only (:name); no string formatting
    params: dict[str, Param] = field(default_factory=dict)


ID = Param("int", min=1, max=1_000_000)

TEMPLATES: dict[str, Template] = {t.name: t for t in [
    Template("task_by_id", "One task by id.",
             "SELECT id, project_id, title, status, due, assignee_id FROM tasks WHERE id = :task_id",
             {"task_id": ID}),
    Template("tasks_by_project", "Tasks in a project, optionally by status, in id order.",
             "SELECT id, title, status, due, assignee_id FROM tasks "
             "WHERE project_id = :project_id AND (:status IS NULL OR status = :status) ORDER BY id",
             {"project_id": ID, "status": Param("enum", required=False, choices=("open", "done"))}),
    Template("overdue_tasks", "Open tasks in a project due before a date, oldest first.",
             "SELECT id, title, due, assignee_id FROM tasks "
             "WHERE project_id = :project_id AND status = 'open' AND due < :as_of ORDER BY due, id",
             {"project_id": ID, "as_of": Param("date")}),
    Template("search_tasks", "Tasks in a project whose title contains some text (case-insensitive).",
             "SELECT id, title, status, due FROM tasks "
             "WHERE project_id = :project_id AND title LIKE :title_contains ESCAPE '\\' ORDER BY id",
             {"project_id": ID, "title_contains": Param("str", max_len=40, like=True)}),
    Template("project_members", "People assigned to tasks in a project. Email and name are redacted.",
             "SELECT DISTINCT users.id, users.display_name, users.email, users.role, users.tz FROM users "
             "JOIN tasks ON tasks.assignee_id = users.id WHERE tasks.project_id = :project_id ORDER BY users.id",
             {"project_id": ID}),
    Template("webhook_failures", "Webhook deliveries in a workspace with at least N attempts.",
             "SELECT id, webhook_id, attempts, status, last_attempt_at FROM webhook_deliveries "
             "WHERE workspace_id = :workspace_id AND attempts >= :min_attempts ORDER BY id",
             {"workspace_id": ID, "min_attempts": Param("int", min=1, max=8)}),
]}
