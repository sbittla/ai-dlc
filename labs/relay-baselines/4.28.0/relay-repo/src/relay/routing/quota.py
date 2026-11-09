"""Daily spend quotas per user, agent, workspace and feature, against denial of wallet (4.28.0; ADR-043).

The rate limit (600 requests a minute per token) bounds how often a caller may ask. It does not bound what
the asking costs: at that rate one token can queue 864,000 triage jobs a day, each a paid model call. A
quota bounds the money instead. Every model call, or every request that will cause one, reserves its
estimated cost against each principal it acts for, and is refused if any of them would pass its daily limit.

Principals are strings `kind:id`: `user:42`, `agent:triage-worker`, `workspace:ws-1`, `feature:triage`.
Limits are USD per UTC day, by kind, with optional overrides for one principal. A principal of a kind with
no limit is refused (fail closed), so a new caller type cannot spend until someone sets its limit.

- `reserve` is all or nothing, in one `BEGIN IMMEDIATE` transaction on a table every process shares, so two
  processes cannot both spend the last dollar. A reservation is keyed by `ref` (an idempotency key): reserving
  the same ref again changes nothing, so a retried request is not charged twice.
- `settle` replaces an estimate with the actual cost once the call has returned. The actual cost is always
  recorded, even when it takes a principal past its limit: money spent is a fact, and the next reserve sees it.
- Every reservation, refusal and settlement is a row in `spend_events`, so a refusal can be explained later.
  Refusals carry the principal that refused, never the request's content. `refusal_counts` gives the
  per-kind counts an alert reads.

If the ledger cannot be written (a locked or missing database) the exception propagates: the caller must
treat that as a refusal, not as permission. The tables belong to `relay.routing`; nothing else writes them.
They are plain SQL that PostgreSQL also accepts; this snapshot runs them on SQLite only.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

QUOTA_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_ledger (
    principal TEXT NOT NULL,
    day       TEXT NOT NULL,              -- UTC calendar day, e.g. '2027-02-15'
    usd       REAL NOT NULL DEFAULT 0,    -- reserved and settled spend so far that day
    PRIMARY KEY (principal, day)
);
CREATE TABLE IF NOT EXISTS spend_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         REAL    NOT NULL,
    ref        TEXT    NOT NULL,
    principals TEXT    NOT NULL,          -- JSON list
    usd        REAL    NOT NULL,
    outcome    TEXT    NOT NULL CHECK (outcome IN ('reserved', 'refused', 'settled')),
    refused_by TEXT
);
CREATE INDEX IF NOT EXISTS spend_events_ref ON spend_events (ref, outcome);
"""


@dataclass(frozen=True)
class QuotaLimits:
    """USD per UTC day by principal kind, and overrides for single principals."""

    by_kind: dict[str, float]
    overrides: dict[str, float] = field(default_factory=dict)

    def limit(self, principal: str) -> float | None:
        if principal in self.overrides:
            return self.overrides[principal]
        kind, sep, ident = principal.partition(":")
        if not sep or not ident:
            return None
        return self.by_kind.get(kind)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    refused_by: str | None = None
    retry_after_s: int = 0
    replayed: bool = False


def utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def seconds_to_next_day(now: float) -> int:
    return max(1, math.ceil(86400 - now % 86400))


class SpendQuota:
    """The shared ledger. One instance per process; each opens its own connection."""

    def __init__(self, path: str, limits: QuotaLimits, timeout_s: float = 5.0) -> None:
        self.limits = limits
        self.conn = sqlite3.connect(path, timeout=timeout_s, isolation_level=None)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(QUOTA_SCHEMA)

    def reserve(self, principals: list[str], usd: float, now: float, ref: str) -> Decision:
        """Reserve `usd` against every principal, or against none. Idempotent per `ref`."""
        if usd < 0 or not principals or not ref:
            raise ValueError("a reservation needs principals, a ref and a non-negative amount")
        day = utc_day(now)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            if self.conn.execute("SELECT 1 FROM spend_events WHERE ref = ? AND outcome = 'reserved'",
                                 (ref,)).fetchone():
                self.conn.execute("COMMIT")
                return Decision(True, replayed=True)
            for p in principals:
                limit = self.limits.limit(p)
                row = self.conn.execute("SELECT usd FROM spend_ledger WHERE principal = ? AND day = ?",
                                        (p, day)).fetchone()
                spent = row[0] if row else 0.0
                if limit is None or spent + usd > limit + 1e-12:
                    self._event(now, ref, principals, usd, "refused", p)
                    self.conn.execute("COMMIT")
                    return Decision(False, p, seconds_to_next_day(now))
            for p in principals:
                self._add(p, day, usd)
            self._event(now, ref, principals, usd, "reserved", None)
            self.conn.execute("COMMIT")
            return Decision(True)
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def settle(self, ref: str, actual_usd: float, now: float) -> None:
        """Replace the reservation `ref` with the actual cost, on the day it was reserved."""
        if actual_usd < 0:
            raise ValueError("actual cost must be non-negative")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute("SELECT at, principals, usd FROM spend_events WHERE ref = ? AND outcome = "
                                    "'reserved'", (ref,)).fetchone()
            if row is None:
                raise KeyError(ref)
            if self.conn.execute("SELECT 1 FROM spend_events WHERE ref = ? AND outcome = 'settled'",
                                 (ref,)).fetchone():
                self.conn.execute("COMMIT")
                return
            at, principals, estimate = row[0], json.loads(row[1]), row[2]
            for p in principals:
                self._add(p, utc_day(at), actual_usd - estimate)
            self._event(now, ref, principals, actual_usd, "settled", None)
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def spent(self, principal: str, now: float) -> float:
        row = self.conn.execute("SELECT usd FROM spend_ledger WHERE principal = ? AND day = ?",
                                (principal, utc_day(now))).fetchone()
        return round(row[0], 9) if row else 0.0

    def refusals(self) -> list[tuple[str, str]]:
        """(ref, principal that refused) for every refusal, in order."""
        return [(r, p) for r, p in self.conn.execute(
            "SELECT ref, refused_by FROM spend_events WHERE outcome = 'refused' ORDER BY id")]

    def refusal_counts(self, since: float, until: float) -> dict[str, int]:
        """Refusals with since <= time < until, counted by the refusing principal's kind (user, agent, ...).

        This is what an alert reads (metric `relay.routing.quota_refusals`, labelled by kind only: a user ID is
        personal data and an unbounded label). The rule that pages on it is ADR-043's merge note for Chapter 16's
        alert rules; nothing in 4.28.0 evaluates it.
        """
        out: dict[str, int] = {}
        for (principal,) in self.conn.execute(
                "SELECT refused_by FROM spend_events WHERE outcome = 'refused' AND at >= ? AND at < ?", (since, until)):
            kind = principal.partition(":")[0]
            out[kind] = out.get(kind, 0) + 1
        return dict(sorted(out.items()))

    def _add(self, principal: str, day: str, usd: float) -> None:
        self.conn.execute(
            "INSERT INTO spend_ledger (principal, day, usd) VALUES (?, ?, ?) "
            "ON CONFLICT (principal, day) DO UPDATE SET usd = usd + excluded.usd", (principal, day, usd))

    def _event(self, now: float, ref: str, principals: list[str], usd: float, outcome: str,
               refused_by: str | None) -> None:
        self.conn.execute("INSERT INTO spend_events (at, ref, principals, usd, outcome, refused_by) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (now, ref, json.dumps(principals), usd, outcome, refused_by))

    def close(self) -> None:
        self.conn.close()
