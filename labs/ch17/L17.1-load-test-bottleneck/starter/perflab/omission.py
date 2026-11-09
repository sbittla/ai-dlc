"""Coordinated omission, simulated: one stall, three ways to measure it (reference solution).

A deterministic model, not a measurement. One server answers requests one at a time in a fixed service time
and stops for a while once (a pause, as a garbage collector, a lock wait or a failover causes). A client is
meant to send a request every `interval_ms`.

- OPEN: every request is sent at its due time whatever happened before, and timed from that time.
- CLOSED, as most simple load tools work: one connection sends the next request only after the previous
  answer arrives, then waits out the interval. During the stall it sends nothing, so it records one slow
  request where a hundred real users would each have waited. That is coordinated omission: the tool
  coordinates with the system it measures and omits the samples that would have been bad (Gil Tene's term).
- CORRECTED: the closed run's samples, plus the samples it should have taken. For each recorded latency L
  longer than the interval, add L - interval, L - 2 x interval, ... while positive. HdrHistogram's
  "record with expected interval" does this; an open schedule avoids needing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .stats import percentile


@dataclass(frozen=True)
class Scenario:
    duration_s: float = 20.0
    interval_ms: float = 10.0       # 100 requests per second intended
    service_ms: float = 1.0
    stall_at_s: float = 5.0
    stall_s: float = 1.0


def serve(start_ms: float, free_ms: float, sc: Scenario) -> float:
    """When a request that reaches the server at `start_ms` finishes, if the server is next free at `free_ms`.

    Service begins at max(start, free). Service cannot run during the stall: a service that would begin
    inside it begins at the stall's end, and one that is running when the stall begins is held for the stall.
    """
    stall_a, stall_b = sc.stall_at_s * 1000, (sc.stall_at_s + sc.stall_s) * 1000
    begin = max(start_ms, free_ms)
    if stall_a <= begin < stall_b:
        begin = stall_b
    end = begin + sc.service_ms
    if begin < stall_a < end:
        end += sc.stall_s * 1000
    return end


def open_loop(sc: Scenario) -> list[float]:
    """TODO 3a. Latencies (ms) of an open schedule: request k is due and sent at k x interval, for every
    k with k x interval < duration; each is timed from its due time. The server is free at 0 and serves in
    order (pass each request's due time and the previous finish to `serve`)."""
    raise NotImplementedError("TODO 3")


def closed_loop(sc: Scenario) -> list[float]:
    """TODO 3b. Latencies (ms) a closed client records. The first request is sent at 0; each next one at
    max(previous send + interval, previous finish), while that time is before the duration. Each is timed from
    its own send."""
    raise NotImplementedError("TODO 3")


def corrected(samples: list[float], interval_ms: float) -> list[float]:
    """TODO 3c. The samples plus, for each sample L > interval, the missing samples L - interval,
    L - 2 x interval, ... while they stay above zero."""
    raise NotImplementedError("TODO 3")


@dataclass(frozen=True)
class View:
    name: str
    samples: int
    p50_ms: float
    p99_ms: float
    p999_ms: float
    max_ms: float


def views(sc: Scenario | None = None) -> list[View]:
    sc = sc or Scenario()
    out = []
    for name, values in (("open schedule, from due time", open_loop(sc)),
                         ("closed loop, from send time", closed_loop(sc)),
                         ("closed loop, corrected", corrected(closed_loop(sc), sc.interval_ms))):
        v = sorted(values)
        out.append(View(name, len(v), percentile(v, 50), percentile(v, 99), percentile(v, 99.9), v[-1]))
    return out
