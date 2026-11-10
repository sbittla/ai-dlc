"""A durable queue for agent jobs, with a dead-letter state, fencing and cancellation (added in 4.30.0; ADR-049).

Chapter 6's triage queue (`relay.worker.queue`) showed the shape: a table, a lease, at-least-once delivery
and a `needs_human` state. Agent jobs need four more things, because one job is a whole agent run that can
take minutes, wait for an approval and spend money:

- **A business key.** `enqueue` deduplicates on (kind, dedup_key), and the key names the work, such as
  `spec-to-pr:RLY-2301`, never a message or delivery ID. A producer that sends the same request twice, or a
  webhook that is redelivered, gets the job that already exists.
- **Fencing.** Every claim takes a new `lease_token`. A worker extends its lease with `heartbeat` between
  steps and writes a result only with its own token, so a worker whose lease expired and was claimed again
  learns that it lost the job and stops before its next effect.
- **A dead-letter state.** A job that keeps failing, that cannot be parsed, or whose agent was revoked goes to
  `dead` with a reason, for a person. Only a person brings it back (`redrive`), and the person is recorded.
- **Cancellation.** A queued job is cancelled at once. A running one is marked, and its worker stops at its
  next heartbeat, between steps, never in the middle of an effect.

A job may also be parked as `waiting` (an approval is pending) and woken when the decision is made.

Retry delays use full jitter: a random delay between zero and the exponential backoff, so a burst of jobs
that failed together does not retry together. The randomness is a hash of the job and the attempt, so the
schedule is reproducible in tests. A provider's Retry-After is a floor: the job never comes back sooner.

Times are seconds since the Unix epoch, passed in by the caller, so tests control the clock.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT    NOT NULL,
    dedup_key       TEXT    NOT NULL,
    payload         TEXT    NOT NULL,
    payload_sha256  TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'waiting', 'done', 'dead', 'cancelled')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL,
    available_at    REAL    NOT NULL,
    lease_owner     TEXT,
    lease_token     INTEGER NOT NULL DEFAULT 0,
    lease_until     REAL,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    cancel_by       TEXT,
    result          TEXT,
    last_error      TEXT,
    dead_reason     TEXT,
    traceparent     TEXT,
    created_at      REAL    NOT NULL,
    updated_at      REAL    NOT NULL,
    UNIQUE (kind, dedup_key)
);
CREATE INDEX IF NOT EXISTS agent_jobs_open ON agent_jobs (status, available_at);
CREATE TABLE IF NOT EXISTS agent_job_events (
    job_id  INTEGER NOT NULL REFERENCES agent_jobs (id),
    at      REAL    NOT NULL,
    event   TEXT    NOT NULL,
    actor   TEXT,
    detail  TEXT    NOT NULL DEFAULT '{}'
);
"""

MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 15.0
BACKOFF_CAP_S = 600.0
FINAL = frozenset({"done", "dead", "cancelled"})


class JobConflict(Exception):
    """The dedup key is already used, for this kind, by a request with a different payload."""


class LeaseLost(Exception):
    """This worker no longer holds the job: its lease expired and another worker claimed it, or it finished."""


class JobCancelled(Exception):
    """A person asked for the job to stop. Raised between steps, never in the middle of an effect."""


@dataclass(frozen=True)
class AgentJob:
    id: int
    kind: str
    dedup_key: str
    payload: dict
    status: str
    attempts: int
    max_attempts: int
    available_at: float
    lease_owner: str | None
    lease_token: int
    lease_until: float | None
    cancel_requested: bool
    result: dict | None
    last_error: str | None
    dead_reason: str | None
    traceparent: str | None
    created_at: float
    updated_at: float


def payload_hash(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jitter_fraction(job_id: int, attempt: int) -> float:
    """A reproducible number in [0, 1) for this job and attempt (full jitter without a random generator)."""
    digest = hashlib.sha256(f"relay-agent-job:{job_id}:{attempt}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def backoff_s(job_id: int, attempt: int, base: float = BACKOFF_BASE_S, cap: float = BACKOFF_CAP_S) -> float:
    """Full-jitter delay before retry `attempt` (1-based): uniform in [0, min(cap, base * 2**(attempt-1)))."""
    return round(jitter_fraction(job_id, attempt) * min(cap, base * 2 ** (attempt - 1)), 3)


def retry_delay_s(job_id: int, attempt: int, retry_after_s: float | None = None) -> float:
    """The delay a failed attempt waits: the jittered backoff, but never less than the provider's Retry-After."""
    delay = backoff_s(job_id, attempt)
    return max(delay, float(retry_after_s)) if retry_after_s is not None else delay


_COLUMNS = ("id, kind, dedup_key, payload, status, attempts, max_attempts, available_at, lease_owner, lease_token, "
            "lease_until, cancel_requested, result, last_error, dead_reason, traceparent, created_at, updated_at")


class AgentJobQueue:
    """The agent job queue. One instance per process; each opens its own connection to the shared file."""

    def __init__(self, path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def _event(self, c, job_id: int, at: float, event: str, actor: str | None = None, **detail) -> None:
        c.execute("INSERT INTO agent_job_events (job_id, at, event, actor, detail) VALUES (?, ?, ?, ?, ?)",
                  (job_id, at, event, actor, json.dumps(detail, sort_keys=True)))

    # ------------------------------------------------------------------ producers

    def enqueue(self, kind: str, dedup_key: str, payload: dict, now: float, max_attempts: int = MAX_ATTEMPTS,
                traceparent: str | None = None) -> tuple[AgentJob, bool]:
        """Add a job, or return the existing one for (kind, dedup_key). Returns (job, created).

        The same key with the same payload is a duplicate delivery and returns the original job, whatever its
        status. The same key with a different payload raises JobConflict: two different requests claim to be
        the same work, and guessing which one was meant would hide a bug.
        """
        if not dedup_key or len(dedup_key) > 200:
            raise ValueError("dedup_key must be 1 to 200 characters")
        digest = payload_hash(payload)
        with self._tx() as c:
            row = c.execute("SELECT id, payload_sha256 FROM agent_jobs WHERE kind = ? AND dedup_key = ?",
                            (kind, dedup_key)).fetchone()
            if row is not None:
                if row[1] != digest:
                    raise JobConflict(f"{kind}:{dedup_key}")
                self._event(c, row[0], now, "duplicate_enqueue")
                job_id, created = row[0], False
            else:
                cur = c.execute(
                    "INSERT INTO agent_jobs (kind, dedup_key, payload, payload_sha256, max_attempts, available_at, "
                    "traceparent, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (kind, dedup_key, json.dumps(payload, sort_keys=True), digest, max_attempts, now, traceparent,
                     now, now))
                job_id, created = cur.lastrowid, True
                self._event(c, job_id, now, "enqueued")
        return self.get(job_id), created

    # ------------------------------------------------------------------ readers

    def get(self, job_id: int) -> AgentJob:
        row = self.conn.execute(f"SELECT {_COLUMNS} FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _to_job(row)

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in ("queued", "running", "waiting", "done", "dead", "cancelled")}
        for status, n in self.conn.execute("SELECT status, COUNT(*) FROM agent_jobs GROUP BY status"):
            out[status] = n
        return out

    def dead_letters(self) -> list[AgentJob]:
        rows = self.conn.execute(f"SELECT {_COLUMNS} FROM agent_jobs WHERE status = 'dead' ORDER BY id").fetchall()
        return [_to_job(r) for r in rows]

    def events(self, job_id: int) -> list[dict]:
        rows = self.conn.execute("SELECT at, event, actor, detail FROM agent_job_events WHERE job_id = ? "
                                 "ORDER BY rowid", (job_id,)).fetchall()
        return [{"at": at, "event": ev, "actor": actor, **json.loads(detail)} for at, ev, actor, detail in rows]

    # ------------------------------------------------------------------ the worker's side

    def claim(self, worker_id: str, now: float, lease_s: float,
              kinds: tuple[str, ...] | None = None) -> AgentJob | None:
        """Take the oldest available job under a new lease token, or None.

        Available means queued with its retry time come, or running under an expired lease. A job whose lease
        expired after its last allowed attempt is not claimed again: it goes to `dead` (`lease_expired`), so a
        job that kills its worker every time reaches a person instead of looping.
        """
        kind_sql, kind_args = "", ()
        if kinds:
            kind_sql = f" AND kind IN ({', '.join('?' for _ in kinds)})"
            kind_args = tuple(kinds)
        with self._tx() as c:
            while True:
                row = c.execute(
                    "SELECT id, status, attempts, max_attempts FROM agent_jobs WHERE ((status = 'queued' AND "
                    f"available_at <= ?) OR (status = 'running' AND lease_until < ?)){kind_sql} ORDER BY id LIMIT 1",
                    (now, now, *kind_args)).fetchone()
                if row is None:
                    return None
                job_id, status, attempts, max_attempts = row
                if status == "running" and attempts >= max_attempts:
                    c.execute("UPDATE agent_jobs SET status = 'dead', dead_reason = 'lease_expired', "
                              "lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ?", (now, job_id))
                    self._event(c, job_id, now, "dead", reason="lease_expired")
                    continue
                if status == "running":
                    self._event(c, job_id, now, "lease_expired")
                c.execute("UPDATE agent_jobs SET status = 'running', lease_owner = ?, lease_token = lease_token + 1, "
                          "lease_until = ?, attempts = attempts + 1, updated_at = ? WHERE id = ?",
                          (worker_id, now + lease_s, now, job_id))
                token = c.execute("SELECT lease_token FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()[0]
                self._event(c, job_id, now, "claimed", worker_id, token=token)
                break
        return self.get(job_id)

    def heartbeat(self, job_id: int, token: int, now: float, lease_s: float) -> None:
        """Extend the lease. Raises LeaseLost if this token no longer holds the job, JobCancelled if a person
        asked the job to stop (the job is then `cancelled`)."""
        cancelled = False
        with self._tx() as c:
            row = c.execute("SELECT cancel_requested, cancel_by FROM agent_jobs WHERE id = ? AND status = 'running' "
                            "AND lease_token = ?", (job_id, token)).fetchone()
            if row is None:
                raise LeaseLost(str(job_id))
            if row[0]:
                c.execute("UPDATE agent_jobs SET status = 'cancelled', lease_owner = NULL, lease_until = NULL, "
                          "updated_at = ? WHERE id = ?", (now, job_id))
                self._event(c, job_id, now, "cancelled", row[1], when="between_steps")
                cancelled = True
            else:
                c.execute("UPDATE agent_jobs SET lease_until = ?, updated_at = ? WHERE id = ?",
                          (now + lease_s, now, job_id))
        if cancelled:  # raised after the commit, so the cancellation is recorded
            raise JobCancelled(str(job_id))

    def complete(self, job_id: int, token: int, result: dict, now: float) -> None:
        with self._tx() as c:
            cur = c.execute("UPDATE agent_jobs SET status = 'done', result = ?, lease_owner = NULL, "
                            "lease_until = NULL, last_error = NULL, updated_at = ? "
                            "WHERE id = ? AND status = 'running' AND lease_token = ?",
                            (json.dumps(result, sort_keys=True), now, job_id, token))
            if cur.rowcount != 1:
                raise LeaseLost(str(job_id))
            self._event(c, job_id, now, "done")

    def park(self, job_id: int, token: int, reason: str, now: float) -> None:
        """Release the job while it waits for something outside it, such as an approval. `wake` requeues it."""
        with self._tx() as c:
            cur = c.execute("UPDATE agent_jobs SET status = 'waiting', last_error = ?, lease_owner = NULL, "
                            "lease_until = NULL, attempts = attempts - 1, updated_at = ? "
                            "WHERE id = ? AND status = 'running' AND lease_token = ?", (reason, now, job_id, token))
            if cur.rowcount != 1:
                raise LeaseLost(str(job_id))
            self._event(c, job_id, now, "waiting", reason=reason)

    def wake(self, job_id: int, now: float, actor: str) -> bool:
        with self._tx() as c:
            cur = c.execute("UPDATE agent_jobs SET status = 'queued', available_at = ?, updated_at = ? "
                            "WHERE id = ? AND status = 'waiting'", (now, now, job_id))
            if cur.rowcount == 1:
                self._event(c, job_id, now, "woken", actor)
            return cur.rowcount == 1

    def fail(self, job_id: int, token: int, error: str, now: float, retryable: bool = True,
             retry_after_s: float | None = None, dead_reason: str | None = None) -> str:
        """Record a failed attempt; returns the new status (`queued` or `dead`). Raises LeaseLost if fenced out.

        A retryable failure is requeued after `retry_delay_s` until the job has used its attempts. A failure
        that is not retryable, or the last attempt's, sends the job to `dead` with `dead_reason` (default: the
        error for a non-retryable failure, `attempts_exhausted` otherwise).
        """
        with self._tx() as c:
            row = c.execute("SELECT attempts, max_attempts FROM agent_jobs WHERE id = ? AND status = 'running' "
                            "AND lease_token = ?", (job_id, token)).fetchone()
            if row is None:
                raise LeaseLost(str(job_id))
            attempts, max_attempts = row
            if retryable and attempts < max_attempts:
                delay = retry_delay_s(job_id, attempts, retry_after_s)
                c.execute("UPDATE agent_jobs SET status = 'queued', available_at = ?, last_error = ?, "
                          "lease_owner = NULL, lease_until = NULL, updated_at = ? WHERE id = ?",
                          (now + delay, error[:200], now, job_id))
                self._event(c, job_id, now, "retry", error=error[:200], delay_s=delay)
                return "queued"
            reason = dead_reason or (error[:200] if not retryable else "attempts_exhausted")
            c.execute("UPDATE agent_jobs SET status = 'dead', dead_reason = ?, last_error = ?, lease_owner = NULL, "
                      "lease_until = NULL, updated_at = ? WHERE id = ?", (reason, error[:200], now, job_id))
            self._event(c, job_id, now, "dead", reason=reason, error=error[:200])
            return "dead"

    # ------------------------------------------------------------------ people's side

    def cancel(self, job_id: int, person: str, now: float) -> str:
        """Ask the job to stop. Returns the status after the request: `cancelled` at once if it was not running,
        `running` (marked) if it was, or the final status it already had."""
        with self._tx() as c:
            status = c.execute("SELECT status FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()[0]
            if status in FINAL:
                return status
            if status == "running":
                c.execute("UPDATE agent_jobs SET cancel_requested = 1, cancel_by = ?, updated_at = ? WHERE id = ?",
                          (person, now, job_id))
                self._event(c, job_id, now, "cancel_requested", person)
                return "running"
            c.execute("UPDATE agent_jobs SET status = 'cancelled', cancel_requested = 1, cancel_by = ?, "
                      "updated_at = ? WHERE id = ?", (person, now, job_id))
            self._event(c, job_id, now, "cancelled", person, when="before_start")
            return "cancelled"

    def redrive(self, job_id: int, proof: dict, reason: str, now: float, authenticate) -> AgentJob:
        """Send a dead job back to the queue with fresh attempts. Only a person may, with a reason.

        `authenticate(proof)` returns the person a fresh person proof names, or raises (for example
        `ApprovalGate.authenticate`, which checks the issuer, the audience and the age, and that the subject is a
        person in the registry). As everywhere in Relay, the proof's signature is checked by a verifier that is
        not built yet (Chapter 13's review); until it is, this binds the redrive to a proof's claims, not to a
        verified signature.
        """
        try:
            person = authenticate(proof)
        except Exception as exc:  # noqa: BLE001 - any refusal of the proof refuses the redrive
            raise PermissionError(f"only a person may redrive a dead job ({exc})") from None
        if len(reason.strip()) < 10:
            raise ValueError("a redrive needs a reason of at least 10 characters")
        with self._tx() as c:
            cur = c.execute("UPDATE agent_jobs SET status = 'queued', attempts = 0, available_at = ?, dead_reason = "
                            "NULL, cancel_requested = 0, updated_at = ? WHERE id = ? AND status = 'dead'",
                            (now, now, job_id))
            if cur.rowcount != 1:
                raise ValueError("only a dead job can be redriven")
            self._event(c, job_id, now, "redriven", person, reason=reason)
        return self.get(job_id)


def _to_job(row: tuple) -> AgentJob:
    (jid, kind, key, payload, status, attempts, max_attempts, available, owner, token, until, cancel, result, err,
     dead, traceparent, created, updated) = row
    return AgentJob(jid, kind, key, json.loads(payload), status, attempts, max_attempts, available, owner, token,
                    until, bool(cancel), json.loads(result) if result else None, err, dead, traceparent, created,
                    updated)
