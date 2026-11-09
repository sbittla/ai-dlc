"""A read-only SQLite connection, enforced by SQLite itself (provided).

The policy in policy.py is the first line of defense. This is the second: even
if a template were wrong, or someone called the connection directly, SQLite
refuses every write, every PRAGMA, ATTACH, non-allowlisted tables and secret
columns, and aborts any query that runs too long.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .templates import ALLOWED_TABLES, SECRET_COLUMNS

MAX_VM_STEPS = 200_000  # SQLite virtual-machine steps per query before it is aborted
_CHECK_EVERY = 1_000

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def authorizer(action: int, arg1, arg2, db_name, trigger) -> int:
    """SQLite authorizer callback: allow reads of allowlisted, non-secret columns; deny everything else."""
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and (arg1 not in ALLOWED_TABLES or arg2 in SECRET_COLUMNS):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class ReadOnlyConnection(sqlite3.Connection):
    """A connection with a per-query step budget. Call reset_budget() before each query."""

    steps = 0

    def reset_budget(self) -> None:
        self.steps = 0

    def _progress(self) -> int:
        self.steps += _CHECK_EVERY
        return 1 if self.steps > MAX_VM_STEPS else 0  # non-zero aborts the running query


def open_readonly(sql_path: Path) -> ReadOnlyConnection:
    """Load the SQL dump into a private in-memory database, then lock it down.

    check_same_thread=False because MCP SDKs may run tool functions in worker
    threads; callers that share the connection must serialize access (server.py
    holds a lock).
    """
    conn = sqlite3.connect(":memory:", factory=ReadOnlyConnection, check_same_thread=False)
    conn.executescript(Path(sql_path).read_text(encoding="utf-8"))
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(authorizer)
    conn.set_progress_handler(conn._progress, _CHECK_EVERY)
    return conn
