"""A rate limiter shared by every service process (added in 4.21.0; ADR-014).

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

Each check is one short transaction on the `rate_limit_windows` table,
serialized by `BEGIN IMMEDIATE`. The table belongs to `relay.service`; no
other module reads or writes it. The statements are plain SQL that
PostgreSQL also accepts, but this snapshot runs and tests them on SQLite
only; the PostgreSQL store adapter is not part of 4.21.0.
"""

from __future__ import annotations

import math
import sqlite3

from .ratelimit import LIMIT_PER_MINUTE, WINDOW_S

SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    token_key    TEXT    NOT NULL,   -- sha256 of the token, never the token
    window_start INTEGER NOT NULL,   -- seconds since the epoch, a multiple of the window
    count        INTEGER NOT NULL,
    PRIMARY KEY (token_key, window_start)
);
"""


class SharedRateLimiter:
    """Fixed one-minute windows per token, counted in a table every process shares."""

    def __init__(self, path: str, limit: int = LIMIT_PER_MINUTE, window_s: float = WINDOW_S,
                 timeout_s: float = 5.0) -> None:
        self.limit, self.window_s = limit, window_s
        self.conn = sqlite3.connect(path, timeout=timeout_s, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def check(self, key: str, now: float) -> tuple[bool, int]:
        """Count one request. Returns (allowed, retry_after_seconds), as `RateLimiter.check` does."""
        start = int(math.floor(now / self.window_s) * self.window_s)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute(
                "SELECT count FROM rate_limit_windows WHERE token_key = ? AND window_start = ?",
                (key, start)).fetchone()
            count = row[0] if row else 0
            if count >= self.limit:
                self.conn.execute("COMMIT")
                return False, max(1, math.ceil(start + self.window_s - now))
            self.conn.execute(
                "INSERT INTO rate_limit_windows (token_key, window_start, count) VALUES (?, ?, 1) "
                "ON CONFLICT (token_key, window_start) DO UPDATE SET count = count + 1",
                (key, start))
            if row is None:  # first request in a new window: drop this token's older windows
                self.conn.execute("DELETE FROM rate_limit_windows WHERE token_key = ? AND window_start < ?",
                                  (key, start))
            self.conn.execute("COMMIT")
            return True, 0
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.conn.close()
