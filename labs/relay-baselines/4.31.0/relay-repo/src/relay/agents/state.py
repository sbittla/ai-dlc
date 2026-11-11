"""Durable run state: runs, a step journal and checkpoints, in SQLite (added in 4.24.0; ADR-026).

The model's context is short-term and is lost when a process stops. The run's state is not: which
task it serves, who asked for it, what it has spent, every step it took and the result of each, and
the checkpoint its policy needs to continue. A run can therefore stop at any point, by crash, budget,
approval or kill switch, and be resumed by another process.

Three rules make resuming safe.

1. Starting a run is idempotent. The same request key returns the same run, so a trigger that fires
   twice starts one run.
2. Every step that is not a read has an idempotency key (`contracts.idempotency_key`; Chapter 6 defined the
   term for a client's retries, and here the runtime computes it), and the journal holds at most one step per
   key. A step is recorded as `started` before its effect and `ok` or
   `error` after it (a write-ahead intent). A repeated call with a key already `ok` returns the
   recorded result and does nothing.
3. A step found `started` on resume has an unknown outcome: the effect may or may not have happened.
   It is run again only if its contract says its handler is idempotent; otherwise the run stops for a
   person (`unknown_outcome`). A step that ended in `error` is retried in the same way: an idempotent
   handler runs again (a transient 502 must not block a pull request for ever); any other error is final
   for its key.

Every write is one `BEGIN IMMEDIATE` transaction, so two processes resuming the same run cannot both
record the same step.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

STATUSES = ("running", "awaiting_approval", "finished", "handed_back", "stopped", "revoked", "delegation_expired",
            "failed")
FINAL = frozenset({"finished", "handed_back", "stopped", "revoked", "failed"})  # delegation_expired can resume

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    design TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    on_behalf_of TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'awaiting_approval', 'finished', 'handed_back',
                                           'stopped', 'revoked', 'delegation_expired', 'failed')),
    reason TEXT,
    budget TEXT NOT NULL DEFAULT '{}',
    checkpoint TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_steps (
    run_id TEXT NOT NULL REFERENCES agent_runs (run_id),
    seq INTEGER NOT NULL,
    idem_key TEXT UNIQUE,
    actor TEXT NOT NULL,
    tool TEXT NOT NULL,
    args_sha256 TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('started', 'ok', 'error', 'refused', 'replayed')),
    result TEXT NOT NULL DEFAULT 'null',
    at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS agent_approvals (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs (run_id),
    tool TEXT NOT NULL,
    args_sha256 TEXT NOT NULL,
    approver_rule TEXT NOT NULL CHECK (approver_rule IN ('requester', 'another_person')),
    requested_by TEXT NOT NULL,
    requested_for TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'expired')),
    decided_by TEXT,
    decided_at TEXT,
    reason TEXT,
    requested_at TEXT NOT NULL,
    expires_at REAL NOT NULL,
    UNIQUE (run_id, tool, args_sha256)
);
"""


class RunStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # ---------------------------------------------------------------- runs

    def start_run(self, request_key: str, task_id: str, design: str, agent_id: str, on_behalf_of: str | None,
                  at: str, budget: dict | None = None) -> tuple[str, bool]:
        """(run_id, created). The run ID is derived from the request key, so a repeated request maps to it."""
        run_id = "run-" + request_key
        with self._tx() as c:
            row = c.execute("SELECT run_id FROM agent_runs WHERE request_key = ?", (request_key,)).fetchone()
            if row:
                return row["run_id"], False
            c.execute("INSERT INTO agent_runs (run_id, request_key, task_id, design, agent_id, on_behalf_of, status,"
                      " budget, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)",
                      (run_id, request_key, task_id, design, agent_id, on_behalf_of, json.dumps(budget or {}), at, at))
        return run_id, True

    def run(self, run_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        out = dict(row)
        out["checkpoint"] = json.loads(out["checkpoint"])
        out["budget"] = json.loads(out["budget"])
        return out

    def set_budget(self, run_id: str, budget: dict, at: str) -> None:
        """Record a run's budget. Only `approval.apply_budget_raise` changes it after the run starts."""
        with self._tx() as c:
            c.execute("UPDATE agent_runs SET budget = ?, updated_at = ? WHERE run_id = ?",
                      (json.dumps(budget, sort_keys=True), at, run_id))

    def set_status(self, run_id: str, status: str, reason: str | None, at: str) -> None:
        if status not in STATUSES:
            raise ValueError(status)
        with self._tx() as c:
            current = c.execute("SELECT status FROM agent_runs WHERE run_id = ?", (run_id,)).fetchone()["status"]
            if current in FINAL:
                raise ValueError(f"run {run_id} is already {current}")
            c.execute("UPDATE agent_runs SET status = ?, reason = ?, updated_at = ? WHERE run_id = ?",
                      (status, reason, at, run_id))

    def save_checkpoint(self, run_id: str, data: dict, at: str) -> None:
        with self._tx() as c:
            c.execute("UPDATE agent_runs SET checkpoint = ?, updated_at = ? WHERE run_id = ?",
                      (json.dumps(data, sort_keys=True), at, run_id))

    # --------------------------------------------------------------- steps

    def begin_step(self, run_id: str, idem_key: str | None, actor: str, tool: str, args_sha: str,
                   at: str) -> tuple[int, dict | None]:
        """Record a step's intent. Returns (seq, None) for a new step, or (seq, existing) when the key is known.

        `existing` is the recorded step (outcome `ok`, `error` or `started`); the caller decides what to
        do with it. A step without a key (a read) is always new.
        """
        with self._tx() as c:
            if idem_key is not None:
                row = c.execute("SELECT * FROM agent_steps WHERE idem_key = ?", (idem_key,)).fetchone()
                if row:
                    return row["seq"], _step(row)
            seq = c.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_steps WHERE run_id = ?",
                            (run_id,)).fetchone()[0]
            c.execute("INSERT INTO agent_steps (run_id, seq, idem_key, actor, tool, args_sha256, outcome, at)"
                      " VALUES (?, ?, ?, ?, ?, ?, 'started', ?)", (run_id, seq, idem_key, actor, tool, args_sha, at))
        return seq, None

    def retry_step(self, run_id: str, seq: int) -> None:
        """Mark a step that ended in `error` as started again (for an idempotent handler's retry)."""
        with self._tx() as c:
            c.execute("UPDATE agent_steps SET outcome = 'started' WHERE run_id = ? AND seq = ? AND outcome = 'error'",
                      (run_id, seq))

    def finish_step(self, run_id: str, seq: int, outcome: str, result) -> None:
        if outcome not in ("ok", "error", "refused"):
            raise ValueError(outcome)
        with self._tx() as c:
            c.execute("UPDATE agent_steps SET outcome = ?, result = ? WHERE run_id = ? AND seq = ?",
                      (outcome, json.dumps(result, sort_keys=True), run_id, seq))

    def note_step(self, run_id: str, actor: str, tool: str, args_sha: str, outcome: str, result, at: str) -> int:
        """A step that has no effect to protect: a refusal, a replay or a read, recorded in one write."""
        with self._tx() as c:
            seq = c.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_steps WHERE run_id = ?",
                            (run_id,)).fetchone()[0]
            c.execute("INSERT INTO agent_steps (run_id, seq, idem_key, actor, tool, args_sha256, outcome, result, at)"
                      " VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
                      (run_id, seq, actor, tool, args_sha, outcome, json.dumps(result, sort_keys=True), at))
        return seq

    def steps(self, run_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM agent_steps WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
        return [_step(r) for r in rows]

    def unfinished_steps(self, run_id: str) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM agent_steps WHERE run_id = ? AND outcome = 'started' ORDER BY seq",
                                 (run_id,)).fetchall()
        return [_step(r) for r in rows]


def _step(row: sqlite3.Row) -> dict:
    out = dict(row)
    out["result"] = json.loads(out["result"])
    return out
