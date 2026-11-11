"""Failures from the outside world, classified, and a circuit breaker per dependency (added in 4.30.0; ADR-049).

An agent worker depends on a model provider, a code host and its own sandbox. Each fails in its own way, and
each failure needs a different answer:

  RateLimited        the provider said 429 and, usually, how long to wait (Retry-After). Retry, never sooner
                     than it asked, and count it towards the breaker.
  DependencyTimeout  no answer in time. Retry with backoff; the call may or may not have happened, so only an
                     idempotent step may be repeated (Chapter 10's journal and the effect ledger decide).
  DependencyError    a 5xx or a broken connection. Retry with backoff and count it.
  PoisonPayload      the job itself cannot be processed (missing fields, wrong types). Never retry: it goes
                     straight to the dead-letter state.

A **circuit breaker** stops a worker from claiming jobs that need a dependency which is failing. After
`threshold` failures within `window_s` it opens and refuses for `cooldown_s`; then it lets one probe through
(half-open). A probe that succeeds closes it, one that fails opens it again. While it is open the queue keeps
the jobs, and their attempts are not spent on calls that would fail.

The clock is passed in, so tests and drills control time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Callable


class RateLimited(Exception):
    def __init__(self, dependency: str, retry_after_s: float | None = None) -> None:
        super().__init__(f"{dependency}: rate limited")
        self.dependency = dependency
        self.retry_after_s = retry_after_s


class DependencyTimeout(Exception):
    def __init__(self, dependency: str, seconds: float) -> None:
        super().__init__(f"{dependency}: no answer within {seconds:g} s")
        self.dependency = dependency


class DependencyError(Exception):
    def __init__(self, dependency: str, status: int | None = None) -> None:
        super().__init__(f"{dependency}: error {status}" if status else f"{dependency}: error")
        self.dependency = dependency
        self.status = status


class PoisonPayload(Exception):
    """The job's payload cannot be processed; retrying cannot help."""


def parse_retry_after(value: str | None, now: float) -> float | None:
    """Seconds to wait from a Retry-After header: delay-seconds or an HTTP date. None if absent or unusable.

    Negative or unparsable values are treated as absent; a value over one hour is capped at one hour, so a
    wrong header cannot park work for a day.
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.isascii() and text.isdigit():
        seconds = float(text)
    else:
        try:
            seconds = parsedate_to_datetime(text).timestamp() - now
        except (TypeError, ValueError, IndexError):
            return None
    if seconds < 0:
        return None
    return min(seconds, 3600.0)


@dataclass
class CircuitBreaker:
    dependency: str
    clock: Callable[[], float]
    threshold: int = 3
    window_s: float = 60.0
    cooldown_s: float = 60.0
    state: str = "closed"
    opened_at: float | None = None
    open_until: float | None = None
    failures: list[float] = field(default_factory=list)
    transitions: list[tuple[float, str]] = field(default_factory=list)
    probing: bool = False

    def _move(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.transitions.append((self.clock(), state))

    def allow(self) -> bool:
        """May a call that needs this dependency start now? In half-open, exactly one probe is let through."""
        now = self.clock()
        if self.state == "open":
            if now < (self.open_until or 0):
                return False
            self._move("half_open")
            self.probing = False
        if self.state == "half_open":
            if self.probing:
                return False
            self.probing = True
            return True
        return True

    def release(self) -> None:
        """Give back a half-open trial slot that no success or failure used. The breaker stays half-open, so the
        next call is the trial. Harmless in any other state."""
        self.probing = False

    def record_success(self) -> None:
        self.failures.clear()
        self.probing = False
        self._move("closed")

    def record_failure(self, retry_after_s: float | None = None) -> None:
        now = self.clock()
        self.probing = False
        if self.state == "half_open":
            self._open(now, retry_after_s)
            return
        self.failures = [t for t in self.failures if now - t < self.window_s] + [now]
        if len(self.failures) >= self.threshold:
            self._open(now, retry_after_s)

    def _open(self, now: float, retry_after_s: float | None) -> None:
        self.opened_at = now
        self.open_until = now + max(self.cooldown_s, retry_after_s or 0.0)
        self.failures.clear()
        self._move("open")
