"""Relay's API rate limit: 600 requests per minute per token (Relay's docs).

A fixed one-minute window per token, kept in process memory. That is exact
for one service process and wrong for several, which would each allow 600:
a known limit of this snapshot, recorded in ADR-007's consequences, and a
reason the limit will move to shared storage when Relay runs more than one
process (Chapter 11).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

LIMIT_PER_MINUTE = 600
WINDOW_S = 60.0


@dataclass
class RateLimiter:
    limit: int = LIMIT_PER_MINUTE
    window_s: float = WINDOW_S
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    def check(self, key: str, now: float) -> tuple[bool, int]:
        """Count one request. Returns (allowed, retry_after_seconds)."""
        start = math.floor(now / self.window_s) * self.window_s
        win_start, count = self._windows.get(key, (start, 0))
        if win_start != start:
            win_start, count = start, 0
        if count >= self.limit:
            return False, max(1, math.ceil(win_start + self.window_s - now))
        self._windows[key] = (win_start, count + 1)
        return True, 0
