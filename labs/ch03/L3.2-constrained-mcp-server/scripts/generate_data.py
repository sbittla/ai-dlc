"""Write Lab 3.2's synthetic Relay test database and its request set into data/.

    python scripts/generate_data.py

data/relay-test.sql     schema and rows for a small synthetic Relay database, as SQL
                        text (a SQLite file is not byte-identical across SQLite
                        versions; the server loads this into memory instead)
data/requests.jsonl     the requests the report replays: legitimate ones and attacks

Everything is synthetic. Names come from short fixed lists; emails use the
reserved example.com domain; hashes are derived from a seed, not from any
password. Output is byte-identical on every platform.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
SEED = 312

SCHEMA = """CREATE TABLE workspaces (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    plan TEXT NOT NULL CHECK (plan IN ('Team', 'Business'))
);
CREATE TABLE users (
    id             INTEGER PRIMARY KEY,
    workspace_id   INTEGER NOT NULL REFERENCES workspaces(id),
    email          TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('Owner', 'Admin', 'Member', 'Guest')),
    tz             TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    api_token_hash TEXT
);
CREATE TABLE projects (
    id           INTEGER PRIMARY KEY,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name         TEXT NOT NULL
);
CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('open', 'done')),
    due         TEXT,
    assignee_id INTEGER REFERENCES users(id)
);
CREATE TABLE webhook_deliveries (
    id              INTEGER PRIMARY KEY,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id),
    webhook_id      INTEGER NOT NULL,
    attempts        INTEGER NOT NULL CHECK (attempts BETWEEN 1 AND 8),
    status          TEXT NOT NULL CHECK (status IN ('delivered', 'retrying', 'degraded')),
    last_attempt_at TEXT NOT NULL
);
"""

FIRST = ["Ana", "Ben", "Cy", "Dee", "Eru", "Fen", "Gus", "Hana", "Ines", "Jo", "Kai", "Lena"]
LAST = ["Okafor", "Ngata", "Silva", "Brandt", "Tanaka", "Moreau", "Patel", "Kowalski"]
ZONES = ["Pacific/Auckland", "Europe/London", "America/New_York", "Asia/Kolkata", "Europe/Berlin", "UTC"]
VERBS = ["Draft", "Review", "Publish", "Fix", "Plan", "Test", "Migrate", "Document"]
OBJECTS = ["release notes", "pricing page", "SSO setup guide", "export job", "webhook retries",
           "onboarding email", "billing report", "Guest permissions", "100% rollout checklist"]


def q(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, row: tuple) -> str:
    return f"INSERT INTO {table} VALUES ({', '.join(q(v) for v in row)});"


def build_sql() -> str:
    rng = random.Random(SEED)
    lines = [SCHEMA]
    lines.append(insert("workspaces", (1, "Relay Demo Co", "Business")))
    lines.append(insert("workspaces", (2, "Kiwi Logistics", "Team")))
    roles = ["Owner", "Admin", "Member", "Member", "Member", "Guest"]
    for uid in range(1, 13):
        ws = 1 if uid <= 6 else 2
        first, last = FIRST[uid - 1], LAST[(uid * 3) % len(LAST)]
        h = hashlib.sha256(f"user-{uid}-{SEED}".encode()).hexdigest()
        token = None if uid % 3 else "sha256$" + hashlib.sha256(f"token-{uid}".encode()).hexdigest()[:40]
        lines.append(insert("users", (uid, ws, f"{first.lower()}.{last.lower()}@example.com", f"{first} {last}",
                                      roles[(uid - 1) % 6], ZONES[uid % len(ZONES)], "pbkdf2$" + h[:48], token)))
    for pid, (ws, name) in enumerate([(1, "Launch"), (1, "Platform"), (2, "Warehouse app"), (2, "Payroll")], 1):
        lines.append(insert("projects", (pid, ws, name)))
    start = date(2026, 10, 1)
    for tid in range(1, 81):
        pid = 1 + (tid - 1) % 4 if tid > 8 else 1
        title = f"{rng.choice(VERBS)} {rng.choice(OBJECTS)}"
        status = "done" if rng.random() < 0.35 else "open"
        due = None if rng.random() < 0.15 else (start + timedelta(days=rng.randrange(0, 75))).isoformat()
        ws_users = range(1, 7) if pid <= 2 else range(7, 13)
        assignee = rng.choice(list(ws_users)) if rng.random() < 0.9 else None
        lines.append(insert("tasks", (tid, pid, title, status, due, assignee)))
    for did in range(1, 31):
        attempts = rng.choice([1, 1, 1, 2, 3, 5, 8])
        status = "degraded" if attempts == 8 else ("retrying" if attempts > 1 and rng.random() < 0.5 else "delivered")
        at = f"2026-11-0{1 + did % 7}T{rng.randrange(0, 24):02d}:{rng.randrange(0, 60):02d}:00Z"
        lines.append(insert("webhook_deliveries", (did, 1 + did % 2, 100 + did % 5, attempts, status, at)))
    return "\n".join(lines) + "\n"


def req(**fields) -> str:
    return json.dumps(fields)


# (id, kind, intent, raw request text). Raw text, so the set can include
# requests that are not JSON at all, or far too large.
REQUESTS = [
    ("L01", "legitimate", "one task by id", req(template="task_by_id", params={"task_id": 7})),
    ("L02", "legitimate", "open tasks in a project", req(template="tasks_by_project", params={"project_id": 1, "status": "open"})),
    ("L03", "legitimate", "overdue tasks", req(template="overdue_tasks", params={"project_id": 2, "as_of": "2026-11-08"})),
    ("L04", "legitimate", "search titles", req(template="search_tasks", params={"project_id": 1, "title_contains": "release"})),
    ("L05", "legitimate", "who works on a project (PII redacted)", req(template="project_members", params={"project_id": 1})),
    ("L06", "legitimate", "degraded webhooks", req(template="webhook_failures", params={"workspace_id": 1, "min_attempts": 8})),
    ("L07", "legitimate", "first page of a project", req(template="tasks_by_project", params={"project_id": 1}, limit=5)),
    ("L08", "legitimate", "a title with a literal %", req(template="search_tasks", params={"project_id": 4, "title_contains": "100%"})),
    ("A01", "attack", "SQL appended to the template name", req(template="tasks_by_project; DROP TABLE tasks", params={"project_id": 1})),
    ("A02", "attack", "free-form SQL field", req(template="task_by_id", params={"task_id": 1}, sql="SELECT * FROM users")),
    ("A03", "attack", "a table as a template name", req(template="users", params={})),
    ("A04", "attack", "SQL in an integer parameter", req(template="tasks_by_project", params={"project_id": "1 OR 1=1"})),
    ("A05", "attack", "boolean where an integer is expected", req(template="task_by_id", params={"task_id": True})),
    ("A06", "attack", "SQL in an enum parameter", req(template="tasks_by_project", params={"project_id": 1, "status": "open' OR '1'='1"})),
    ("A07", "attack", "UNION in a text parameter", req(template="search_tasks", params={"project_id": 1, "title_contains": "' UNION SELECT email FROM users --"})),
    ("A08", "attack", "LIKE wildcard to match everything", req(template="search_tasks", params={"project_id": 1, "title_contains": "%"})),
    ("A09", "attack", "an extra parameter naming a secret column", req(template="tasks_by_project", params={"project_id": 1, "columns": "password_hash"})),
    ("A10", "attack", "row limit far above the cap", req(template="tasks_by_project", params={"project_id": 1}, limit=10000)),
    ("A11", "attack", "negative row limit", req(template="tasks_by_project", params={"project_id": 1}, limit=-1)),
    ("A12", "attack", "a 5,000-character parameter", req(template="search_tasks", params={"project_id": 1, "title_contains": "a" * 5000})),
    ("A13", "attack", "a parameter one character too long", req(template="search_tasks", params={"project_id": 1, "title_contains": "a" * 41})),
    ("A14", "attack", "an id out of range", req(template="task_by_id", params={"task_id": 10 ** 12})),
    ("A15", "attack", "SQL in a date parameter", req(template="overdue_tasks", params={"project_id": 1, "as_of": "2026-11-08'; DROP TABLE tasks; --"})),
    ("A16", "attack", "a control character in text", req(template="search_tasks", params={"project_id": 1, "title_contains": "abc\u0000"})),
    ("A17", "attack", "raw SQL instead of a request", "SELECT email, password_hash FROM users"),
    ("A18", "attack", "parameters as a list", req(template="task_by_id", params=[7])),
]


def main() -> None:
    DATA.mkdir(exist_ok=True)
    (DATA / "relay-test.sql").write_bytes(build_sql().encode("utf-8"))
    with (DATA / "requests.jsonl").open("wb") as f:
        for rid, kind, intent, raw in REQUESTS:
            f.write((json.dumps({"id": rid, "kind": kind, "intent": intent, "request": raw}) + "\n").encode("utf-8"))
    print(f"wrote data/relay-test.sql and {len(REQUESTS)} requests to data/requests.jsonl")


if __name__ == "__main__":
    main()
