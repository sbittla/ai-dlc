"""A durable triage queue on SQLite, with idempotency keys and leases.

The queue is one table, `triage_jobs`, in Relay's own database. The worker
module owns it: no other module reads or writes it except through
`TriageQueue` (ADR-007). A job moves through four states:

    queued -> running -> done
                      -> queued again (retry, after a backoff)
                      -> needs_human (attempts exhausted, or output unusable)

Delivery is at least once. A worker holds a job under a lease; if it dies,
the lease expires and another worker claims the job again. A worker whose
lease has expired cannot complete the job, because every write checks the
lease owner (a simple fencing rule).

Times are seconds since the Unix epoch, passed in by the caller, so tests
control the clock.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS triage_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace       TEXT    NOT NULL,
    idempotency_key TEXT    NOT NULL,
    body_sha256     TEXT    NOT NULL,
    ticket_text     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'done', 'needs_human')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    available_at    REAL    NOT NULL,
    lease_owner     TEXT,
    lease_until     REAL,
    result          TEXT,   -- JSON: the triage suggestion; never applied to a task here
    last_error      TEXT,
    created_at      REAL    NOT NULL,
    updated_at      REAL    NOT NULL,
    UNIQUE (workspace, idempotency_key)
);
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id    TEXT PRIMARY KEY,
    last_pass_at REAL NOT NULL
);
"""

MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 10.0  # retry delays 10 s, 20 s, 40 s ... (no jitter, so tests are exact)
BACKOFF_CAP_S = 300.0


class IdempotencyConflict(Exception):
    """The idempotency key was already used, in this workspace, for a different request body."""


@dataclass(frozen=True)
class Job:
    id: int
    workspace: str
    idempotency_key: str
    ticket_text: str
    status: str
    attempts: int
    available_at: float
    lease_owner: str | None
    lease_until: float | None
    result: dict | None
    last_error: str | None
    created_at: float
    updated_at: float


def body_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def backoff_s(attempts: int) -> float:
    """Delay before retry number `attempts` (1-based): 10, 20, 40, ... seconds, capped at 300."""
    return min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** (attempts - 1))


_COLUMNS = ("id, workspace, idempotency_key, ticket_text, status, attempts, available_at, "
            "lease_owner, lease_until, result, last_error, created_at, updated_at")


class TriageQueue:
    """The triage queue. One instance per process; each opens its own connection."""

    def __init__(self, path: str = ":memory:", max_attempts: int = MAX_ATTEMPTS) -> None:
        # isolation_level=None: we issue BEGIN IMMEDIATE ourselves, so a claim is atomic
        # across processes that share the database file.
        self.conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.max_attempts = max_attempts

    # ------------------------------------------------------------ producers

    def enqueue(self, workspace: str, key: str, text: str, now: float) -> tuple[Job, bool]:
        """Add a job, or return the existing one for this (workspace, key).

        Returns (job, created). The same key with the same body is a replay and
        returns the original job with created=False. The same key with a different
        body raises IdempotencyConflict: the caller has a bug, and guessing which
        request it meant would hide it.
        """
        digest = body_hash(text)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                f"SELECT {_COLUMNS}, body_sha256 FROM triage_jobs WHERE workspace = ? AND idempotency_key = ?",
                (workspace, key)).fetchone()
            if row is not None:
                self.conn.execute("COMMIT")
                if row[-1] != digest:
                    raise IdempotencyConflict(key)
                return _to_job(row[:-1]), False
            cur = self.conn.execute(
                "INSERT INTO triage_jobs (workspace, idempotency_key, body_sha256, ticket_text, status, "
                "available_at, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)",
                (workspace, key, digest, text, now, now, now))
            self.conn.execute("COMMIT")
        except IdempotencyConflict:
            raise
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(cur.lastrowid), True

    # ------------------------------------------------------------ readers

    def get(self, job_id: int) -> Job:
        row = self.conn.execute(f"SELECT {_COLUMNS} FROM triage_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _to_job(row)

    def counts(self) -> dict[str, int]:
        out = {"queued": 0, "running": 0, "done": 0, "needs_human": 0}
        for status, n in self.conn.execute("SELECT status, COUNT(*) FROM triage_jobs GROUP BY status"):
            out[status] = n
        return out

    def last_pass_at(self) -> float | None:
        row = self.conn.execute("SELECT MAX(last_pass_at) FROM worker_heartbeats").fetchone()
        return row[0]

    # ------------------------------------------------------------ the worker's side

    def heartbeat(self, worker_id: str, now: float) -> None:
        self.conn.execute(
            "INSERT INTO worker_heartbeats (worker_id, last_pass_at) VALUES (?, ?) "
            "ON CONFLICT (worker_id) DO UPDATE SET last_pass_at = excluded.last_pass_at", (worker_id, now))

    def claim(self, worker_id: str, now: float, lease_s: float) -> Job | None:
        """Take the oldest available job under a lease, or None if there is none.

        A job is available if it is queued and its retry time has come, or if it
        is running under a lease that has expired (its worker died).
        """
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT id FROM triage_jobs WHERE (status = 'queued' AND available_at <= ?) "
                "OR (status = 'running' AND lease_until < ?) ORDER BY id LIMIT 1", (now, now)).fetchone()
            if row is None:
                self.conn.execute("COMMIT")
                return None
            self.conn.execute(
                "UPDATE triage_jobs SET status = 'running', lease_owner = ?, lease_until = ?, "
                "attempts = attempts + 1, updated_at = ? WHERE id = ?", (worker_id, now + lease_s, now, row[0]))
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(row[0])

    def complete(self, job_id: int, worker_id: str, result: dict, now: float) -> bool:
        """Record the result. False (and no change) if this worker no longer holds the lease."""
        cur = self.conn.execute(
            "UPDATE triage_jobs SET status = 'done', result = ?, lease_owner = NULL, lease_until = NULL, "
            "last_error = NULL, updated_at = ? WHERE id = ? AND status = 'running' AND lease_owner = ?",
            (json.dumps(result, sort_keys=True), now, job_id, worker_id))
        return cur.rowcount == 1

    def fail(self, job_id: int, worker_id: str, error: str, now: float, retryable: bool = True) -> str | None:
        """Record a failed attempt. Returns the new status, or None if the lease was lost.

        A retryable failure goes back to the queue after a backoff until the job has
        used `max_attempts`; then, or for a non-retryable failure, it goes to
        `needs_human`, the queue a person works through. A failure is never
        turned into a guessed answer.
        """
        job = self.get(job_id)
        if job.status != "running" or job.lease_owner != worker_id:
            return None
        if retryable and job.attempts < self.max_attempts:
            status, available = "queued", now + backoff_s(job.attempts)
        else:
            status, available = "needs_human", job.available_at
        self.conn.execute(
            "UPDATE triage_jobs SET status = ?, available_at = ?, lease_owner = NULL, lease_until = NULL, "
            "last_error = ?, updated_at = ? WHERE id = ?", (status, available, error[:200], now, job_id))
        return status


def _to_job(row: tuple) -> Job:
    (jid, ws, key, text, status, attempts, available, owner, until, result, err, created, updated) = row
    return Job(jid, ws, key, text, status, attempts, available, owner, until,
               json.loads(result) if result else None, err, created, updated)
