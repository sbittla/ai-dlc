"""How many triage workers the ticket arrivals need: Relay's real worker and queue, in simulated time.

The worker, the queue and the simulated triage model are Relay 4.28.0's own code. Only the clock is
simulated: a worker that claims a job is busy until the simulated call returns (or times out), and an idle
worker sleeps its poll interval, as `Worker.run` does. Arrivals come from the generated week's per-minute
ticket counts, spread within each minute by a fixed seed. The triage model's latency is the simulator's
configuration (median 2.4 s), so these are statements about that configuration, not about a real model.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass

from .stats import percentile
from .workload import load_traffic

BASE = 1_801_440_000.0  # 2027-02-01T00:00:00Z: minute 0 of the generated week
SCENARIOS = {"peak-hour": (540, 60), "outage": (2 * 1440 + 14 * 60, 60)}  # (first minute, minutes)
TEMPLATES = ("The export button returns a 500 error for our whole team.", "How do I move a task to another project?",
             "We were charged twice this month.", "SSO login fails with an expired certificate.",
             "Could you add a dark mode to the task board?")


def arrivals(scenario: str, seed: int = 1717) -> list[float]:
    """Ticket arrival times (epoch seconds) in a scenario's window: each minute's count, at uniform random seconds."""
    first, minutes = SCENARIOS[scenario]
    journeys, rows = load_traffic()
    col = journeys.index("post_triage_job")
    rng = random.Random(seed)
    out = []
    for m in range(first, first + minutes):
        out += sorted(BASE + m * 60 + round(rng.random() * 60, 3) for _ in range(rows[m][col]))
    return out


class SimClock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class Recording:
    """Passes calls to a triage client and remembers the last call's latency."""

    def __init__(self, inner) -> None:
        self.inner, self.model, self.prompt, self.last = inner, inner.model, inner.prompt, 0.0

    def classify(self, text: str, attempt: int):
        outcome = self.inner.classify(text, attempt)
        self.last = outcome.latency_s
        return outcome


@dataclass(frozen=True)
class CapacityResult:
    scenario: str
    workers: int
    tickets: int
    done: int
    needs_human: int
    p50_s: float
    p95_s: float
    max_s: float
    max_queued: int
    longest_gap_s: float   # longest time a worker went between passes (ESC-N09: escalation passes run each pass)


def simulate(times: list[float], workers: int, triage=None, timeout_s: float = 10.0, poll_s: float = 1.0,
             scenario: str = "") -> CapacityResult:
    """TODO 5. Run `workers` Relay workers over these arrivals in simulated time.

    Use one TriageQueue(":memory:"), one SimClock starting at times[0], and Worker(queue, Recording(triage),
    worker_id=f"worker-{i + 1}", clock=clock, timeout_s=timeout_s) for each worker (triage defaults to Relay's
    SimulatedTriage()). Keep a heap of (time, worker index), all starting at times[0]. Repeatedly pop the
    earliest; first enqueue every arrival due by then (workspace "ws-1", key f"ticket-{n:05d}",
    text f"{TEMPLATES[n % 5]} (ticket {n})", now = its arrival time); set the clock; run_once. If the
    result is "idle": stop that worker when every arrival is enqueued and the queue holds nothing queued or
    running, else push it back at time + poll_s. Otherwise push it back at time + min(latency, timeout_s).
    Track the most jobs queued at any pop and each worker's longest gap between passes.
    Time to suggestion is a done job's updated_at - created_at; report its nearest-rank p50, p95 and max.
    """
    from relay.worker import TriageQueue, Worker
    from relay.worker.triage import SimulatedTriage

    queue = TriageQueue(":memory:")
    clock = SimClock(times[0])
    rec = Recording(triage or SimulatedTriage())
    pool = [Worker(queue, rec, worker_id=f"worker-{i + 1}", clock=clock, timeout_s=timeout_s) for i in range(workers)]
    heap = [(times[0], i) for i in range(workers)]
    heapq.heapify(heap)
    nxt, max_queued, gaps, last = 0, 0, [0.0] * workers, [times[0]] * workers
    while heap:
        t, i = heapq.heappop(heap)
        while nxt < len(times) and times[nxt] <= t:
            queue.enqueue("ws-1", f"ticket-{nxt:05d}", f"{TEMPLATES[nxt % 5]} (ticket {nxt})", times[nxt])
            nxt += 1
        counts = queue.counts()
        max_queued = max(max_queued, counts["queued"])
        gaps[i], last[i] = max(gaps[i], t - last[i]), t
        clock.t = t
        if pool[i].run_once() == "idle":
            if nxt >= len(times) and counts["queued"] + counts["running"] == 0:
                continue
            heapq.heappush(heap, (t + poll_s, i))
        else:
            heapq.heappush(heap, (t + min(rec.last, timeout_s), i))
    jobs = [queue.get(j) for j in range(1, len(times) + 1)]
    waits = sorted(j.updated_at - j.created_at for j in jobs if j.status == "done")
    return CapacityResult(scenario, workers, len(times), len(waits), sum(j.status == "needs_human" for j in jobs),
                          round(percentile(waits, 50), 3), round(percentile(waits, 95), 3), round(waits[-1], 3),
                          max_queued, round(max(gaps), 3))


def table(scenarios=("peak-hour", "outage"), worker_counts=(1, 2, 3)) -> list[CapacityResult]:
    return [simulate(arrivals(s), w, scenario=s) for s in scenarios for w in worker_counts]
