"""The effect ledger: an external effect happens at most once per business key (added in 4.30.0; ADR-049).

Chapter 10's run journal makes a step idempotent within one run: its key covers the run, the tool and the
arguments. That does not help when the same work arrives as two runs, for example when a queue delivers a
message twice and the second delivery starts a second run. Each run then has its own keys, and each would
perform the effect.

The ledger closes that gap for effects that matter outside Relay: a pull request, a refund, a message to a
customer. Each effect has a **natural key** taken from the business object it acts on, such as
`pr:RLY-2301` or `refund:ch_0042`, never from a run, a message or a delivery. The ledger records the key
before the effect (`started`) and the result after it (`ok`), in one shared table, and:

- a repeat of a key already `ok`, from any run or worker, returns the recorded result and does nothing;
- a repeat with different arguments for the same key is refused (`EffectConflict`): two runs disagree about
  what the one effect should be, and a person decides;
- a key found `started` has an unknown outcome. If the provider honours an idempotency key (as many payment
  and messaging APIs do), the call is repeated with the same key and the provider deduplicates it. If not, the
  ledger refuses (`UnknownEffectOutcome`) and a person checks before anything is repeated.

The key is passed to the provider as its idempotency key, so the provider's own deduplication and the
ledger agree on what "the same effect" means.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_effects (
    effect_key   TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    args_sha256  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('started', 'ok')),
    first_run    TEXT NOT NULL,
    result       TEXT,
    attempts     INTEGER NOT NULL DEFAULT 1,
    started_at   REAL,
    replays      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


class EffectConflict(Exception):
    """The key is recorded with different arguments."""


class UnknownEffectOutcome(Exception):
    """The effect was started and never recorded, and the provider cannot deduplicate a repeat."""


def args_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class EffectLedger:
    def __init__(self, path: str = ":memory:", stamp: Callable[[], str] | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        self.conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.stamp = stamp or (lambda: "")
        import time
        self.clock = clock or time.time

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def perform(self, effect_key: str, kind: str, args: dict, run_id: str,
                call: Callable[[str, dict], dict], provider_idempotent: bool = False,
                provider_window_s: float | None = None) -> tuple[dict, bool]:
        """Perform `call(effect_key, args)` at most once for `effect_key`. Returns (result, replayed).

        Providers keep idempotency keys for a limited time. Past `provider_window_s` since the effect was started,
        a repeat could create the effect a second time, so a started effect that old is refused as
        `UnknownEffectOutcome` even for an idempotent provider: look before you create, or ask a person.
        """
        sha = args_hash(args)
        with self._tx() as c:
            row = c.execute("SELECT kind, args_sha256, status, result, started_at FROM agent_effects "
                            "WHERE effect_key = ?",
                            (effect_key,)).fetchone()
            if row is None:
                c.execute("INSERT INTO agent_effects (effect_key, kind, args_sha256, status, first_run, started_at, "
                          "created_at, updated_at) VALUES (?, ?, ?, 'started', ?, ?, ?, ?)",
                          (effect_key, kind, sha, run_id, self.clock(), self.stamp(), self.stamp()))
            else:
                if row[0] != kind or row[1] != sha:
                    raise EffectConflict(effect_key)
                if row[2] == "ok":
                    c.execute("UPDATE agent_effects SET replays = replays + 1, updated_at = ? WHERE effect_key = ?",
                              (self.stamp(), effect_key))
                    return json.loads(row[3]), True
                if not provider_idempotent:
                    raise UnknownEffectOutcome(effect_key)
                if provider_window_s is not None and row[4] is not None and self.clock() - row[4] > provider_window_s:
                    raise UnknownEffectOutcome(f"{effect_key}: started past the provider's key window")
                c.execute("UPDATE agent_effects SET attempts = attempts + 1, updated_at = ? WHERE effect_key = ?",
                          (self.stamp(), effect_key))
        result = call(effect_key, args)  # outside the transaction: a provider call must not hold the write lock
        with self._tx() as c:
            c.execute("UPDATE agent_effects SET status = 'ok', result = ?, updated_at = ? WHERE effect_key = ?",
                      (json.dumps(result, sort_keys=True), self.stamp(), effect_key))
        return result, False

    def get(self, effect_key: str) -> dict | None:
        row = self.conn.execute("SELECT effect_key, kind, status, first_run, result, attempts, replays FROM "
                                "agent_effects WHERE effect_key = ?", (effect_key,)).fetchone()
        if row is None:
            return None
        return {"effect_key": row[0], "kind": row[1], "status": row[2], "first_run": row[3],
                "result": json.loads(row[4]) if row[4] else None, "attempts": row[5], "replays": row[6]}

    def counts(self) -> dict[str, int]:
        out = {"started": 0, "ok": 0, "replays": 0}
        for status, n, replays in self.conn.execute(
                "SELECT status, COUNT(*), COALESCE(SUM(replays), 0) FROM agent_effects GROUP BY status"):
            out[status] = n
            out["replays"] += replays
        return out
