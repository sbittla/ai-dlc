"""A rate limiter shared by every service process (added in 4.21.0; ADR-014; leases from 4.28.0, ADR-041).

Relay's limit is 600 requests per minute per token (Relay's docs). The
4.19.0 limiter (`ratelimit.RateLimiter`) keeps its counts in process memory,
so two processes would each allow 600. From 4.21.0 the container runs the
WSGI application in more than one process (ADR-015), so the count moves to
the database every process already shares.

The window rule is the same as `RateLimiter`'s: a fixed one-minute window
per token hash, with the same `check(key, now)` interface, so `RelayApp`
accepts either through its `limiter` argument. The known limits carry over:
a fixed window allows a burst of up to twice the limit across a window edge,
and requests with no valid token are refused before the limiter counts them.

4.21.0 counted every request in its own write transaction, serialized by
`BEGIN IMMEDIATE`: one database write per API request, reads included, on the
lock the worker's queue and escalation pass also take. Chapter 17's load test
measured that cost (ADR-041). From 4.28.0 a process leases a block of counts
in one transaction and spends the lease from memory:

- A lease is at most `block` counts and never more than the window has left,
  so the processes together never admit more than the limit (no over-admission).
- Leases end with their window. Counts a process leased but did not use are
  not returned, so a token can be refused early by at most
  (processes - 1) x (block - 1) requests in a window, when other processes hold
  unused leases. With two processes and a block of 10 that is 9 of 600.
- With one process, every decision is the same as the exact limiter's.
- Once the window's count reaches the limit, the refusal is remembered until
  the window ends, so a token flooding past its limit costs at most one write per process per window (the
  lease that finds the window full) and none after it.

`block=1` is the 4.21.0 behaviour: exact, one transaction per request.
`transactions` counts the write transactions this instance has issued; the
load test and `tests/test_service_sharedlimit.py` read it.

The table belongs to `relay.service`; no other module reads or writes it. The
statements are plain SQL that PostgreSQL also accepts, but this snapshot runs
and tests them on SQLite only; the PostgreSQL store adapter is not part of it.
"""

from __future__ import annotations

import math
import sqlite3

from .ratelimit import LIMIT_PER_MINUTE, WINDOW_S

LEASE_BLOCK = 10  # counts leased per transaction (ADR-041); 1 = exact, one write per request

SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    token_key    TEXT    NOT NULL,   -- sha256 of the token, never the token
    window_start INTEGER NOT NULL,   -- seconds since the epoch, a multiple of the window
    count        INTEGER NOT NULL,   -- counts admitted or leased to a process in this window
    PRIMARY KEY (token_key, window_start)
);
"""


class SharedRateLimiter:
    """Fixed one-minute windows per token, counted in a table every process shares, leased in blocks."""

    def __init__(self, path: str, limit: int = LIMIT_PER_MINUTE, window_s: float = WINDOW_S,
                 timeout_s: float = 5.0, block: int = LEASE_BLOCK) -> None:
        if block < 1 or limit < 1:
            raise ValueError("limit and block must be at least 1")
        self.limit, self.window_s, self.block = limit, window_s, block
        self.conn = sqlite3.connect(path, timeout=timeout_s, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.transactions = 0
        self._left: dict[str, tuple[int, int]] = {}  # token key -> (window start, leased counts not yet used)
        self._full: dict[str, int] = {}              # token key -> window start whose count reached the limit

    def check(self, key: str, now: float) -> tuple[bool, int]:
        """Count one request. Returns (allowed, retry_after_seconds), as `RateLimiter.check` does."""
        start = int(math.floor(now / self.window_s) * self.window_s)
        retry = max(1, math.ceil(start + self.window_s - now))
        if self._full.get(key) == start:
            return False, retry
        win, left = self._left.get(key, (start, 0))
        if win == start and left > 0:
            self._left[key] = (start, left - 1)
            return True, 0
        granted = self._lease(key, start)
        if granted == 0:
            self._left.pop(key, None)
            self._full[key] = start
            return False, retry
        self._left[key] = (start, granted - 1)
        if len(self._left) > 4096 or len(self._full) > 4096:  # forget other tokens' finished windows
            self._left = {k: v for k, v in self._left.items() if v[0] >= start}
            self._full = {k: v for k, v in self._full.items() if v >= start}
        return True, 0

    def _lease(self, key: str, start: int) -> int:
        """One write transaction: lease up to `block` counts in this window. Returns how many (0 if full)."""
        self.transactions += 1
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT count FROM rate_limit_windows WHERE token_key = ? AND window_start = ?",
                (key, start)).fetchone()
            count = row[0] if row else 0
            granted = min(self.block, self.limit - count)
            if granted <= 0:
                self.conn.execute("COMMIT")
                return 0
            self.conn.execute(
                "INSERT INTO rate_limit_windows (token_key, window_start, count) VALUES (?, ?, ?) "
                "ON CONFLICT (token_key, window_start) DO UPDATE SET count = count + excluded.count",
                (key, start, granted))
            if row is None:  # first lease in a new window: drop this token's older windows
                self.conn.execute("DELETE FROM rate_limit_windows WHERE token_key = ? AND window_start < ?",
                                  (key, start))
            self.conn.execute("COMMIT")
            return granted
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.conn.close()
