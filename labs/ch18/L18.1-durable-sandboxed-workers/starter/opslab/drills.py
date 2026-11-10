"""Fault-injection drills on the helper as a queue worker (Relay 4.30.0). TODO 3 is `verdict`.

Each drill builds a fresh deployment in a temporary folder, injects one fault, runs workers until nothing is
left to do, and observes what happened: the job's and the run's final status, how many pull requests the code
host created, the worker outcomes, and any refusals. `data/drills.json` says what each drill must produce.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import DATA
from .world import ESCAPING_CODE, Clock, Crash, World
from relay.agentops import SharedRegistry
from relay.agentops.resilience import DependencyTimeout, RateLimited
from relay.audit import AuditTrail, killswitch

RUN = "run-spec-to-pr:{task}"


def load_drills() -> list[dict]:
    return json.loads((DATA / "drills.json").read_text(encoding="utf-8"))["drills"]


def _observe(w: World, outcomes: list[str], task: str = "RLY-2301", **extra) -> dict:
    job = w.queue.conn.execute("SELECT id FROM agent_jobs WHERE dedup_key = ?", (task,)).fetchone()
    j = w.queue.get(job[0])
    try:
        run = w.store.run(RUN.format(task=task))
        run_status, run_reason = run["status"], run["reason"]
    except KeyError:
        run_status, run_reason = None, None
    runs = w.store.conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
    return {"job": j.status, "dead_reason": j.dead_reason, "run": run_status, "run_reason": run_reason,
            "prs": w.host.creates, "runs": runs, "attempts": j.attempts, "outcomes": outcomes, **extra}


def _until_quiet(w: World, worker, outcomes: list[str], step_s: float = 5.0, limit: int = 60) -> None:
    for _ in range(limit):
        out = worker.run_once()
        outcomes.append(out)
        if out == "waiting" and w.approve_and_wake() == 0:
            pass
        if out == "waiting":
            w.clock.t += 600  # the requester reads the diff and approves ten minutes later
            w.approve_and_wake()
        elif out in ("idle", "paused"):
            pending = w.queue.conn.execute("SELECT MIN(available_at) FROM agent_jobs WHERE status = 'queued'"
                                           ).fetchone()[0]
            if pending is None and out == "idle":
                return
            w.clock.t = max(w.clock.t + step_s, pending or 0)


def f0(root: Path) -> dict:
    w = World(root)
    w.enqueue()
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    return _observe(w, outcomes)


def f1(root: Path) -> dict:
    clock = Clock()
    w = World(root, clock)
    w.enqueue()
    first = w.worker("worker-1")
    outcomes = [first.run_once()]
    clock.t += 600
    w.approve_and_wake()
    w.host.crash_after_create = True
    try:
        first.run_once()
    except Crash:
        outcomes.append("crashed")
    clock.t += 121  # the dead worker's lease expires
    replacement = World(root, clock)  # a new process: every object rebuilt from the shared files
    _until_quiet(replacement, replacement.worker("worker-2"), outcomes)
    return _observe(replacement, outcomes, ledger_attempts=replacement.ledger.get("pr:RLY-2301")["attempts"])


def f2(root: Path) -> dict:
    w = World(root)
    _, created_first = w.enqueue()
    w.clock.t += 31
    _, created_again = w.enqueue()  # the producer's retry: the same request, delivered again
    second = World(root, w.clock).worker("worker-2")
    polls: list[str] = []
    w.on_sandbox = lambda result: polls.append(second.run_once())  # another worker polls during the long step
    outcomes: list[str] = []
    _until_quiet(w, w.worker("worker-1"), outcomes)
    return _observe(w, outcomes, second_worker=polls, duplicate_created=created_again,
                    lease_s=w.lease_s, run_tests_s=100)


def f3(root: Path) -> dict:
    w = World(root)
    w.queue.enqueue("spec-to-pr", "RLY-2301", {"task_id": "RLY-2301", "agent_id": "spec-to-pr-helper",
                                               "on_behalf_of": "priya.n"}, w.clock(), max_attempts=4)
    w.model_fault = lambda now: DependencyTimeout("model", 30)
    w.breaker.threshold = 99  # one job: the breaker is not what this drill is about
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    delays = [e["delay_s"] for e in w.queue.events(1) if e["event"] == "retry"]
    return _observe(w, outcomes, retry_delays_s=delays)


def f4(root: Path) -> dict:
    w = World(root)
    for n in (1, 2, 3, 4):
        w.enqueue(f"RLY-230{n}")
    until = w.clock() + 100
    w.model_fault = lambda now: RateLimited("model", 30.0) if now < until else None
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    obs = _observe(w, outcomes)
    jobs = [w.queue.get(n) for n in (1, 2, 3, 4)]
    obs.update({"job": "done" if all(j.status == "done" for j in jobs) else "mixed", "prs": w.host.creates,
                "paused": "paused" in outcomes, "rate_limited_attempts": outcomes.count("retry"),
                "breaker": [(round(t - w.clock.t, 0), s) for t, s in w.breaker.transitions],
                "breaker_states": [s for _, s in w.breaker.transitions]})
    return obs


def f5(root: Path) -> dict:
    w = World(root, code=ESCAPING_CODE)
    w.enqueue()
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    refused = [r["reason"] for res in w.sandbox_results for r in res.refusals]
    return _observe(w, outcomes, refused=refused)


def f6(root: Path) -> dict:
    w = World(root)
    w.enqueue()
    monitor = SharedRegistry(json.loads(json.dumps(__import__("opslab.world", fromlist=["REGISTRY"]).REGISTRY)),
                             str(Path(root) / "relay.db"), clock=w.clock)
    tripped = {}

    def trip(result):
        killswitch.trip(monitor, AuditTrail(), "spec-to-pr-helper", "detection:DR-003", "drill F6", now=w.clock())
        tripped["at"] = w.clock()
    w.on_sandbox = trip
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    refusal = [r for r in w.trail.records if r["outcome"] == "refused"][-1]
    return _observe(w, outcomes, refusal_code=refusal["detail"]["code"], refused_tool=refusal["detail"]["tool"],
                    trip_to_refusal_s=round(_seconds(refusal["at"]) - tripped["at"], 1))


def _seconds(stamp: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def f7(root: Path) -> dict:
    w = World(root)
    w.enqueue()
    w.on_sandbox = lambda result: w.queue.cancel(1, "priya.n", w.clock())
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    return _observe(w, outcomes)


def f8(root: Path) -> dict:
    w = World(root)
    w.enqueue(payload={"agent_id": "spec-to-pr-helper", "on_behalf_of": "priya.n"})
    outcomes: list[str] = []
    _until_quiet(w, w.worker(), outcomes)
    return _observe(w, outcomes)


RUNNERS = {"F0": f0, "F1": f1, "F2": f2, "F3": f3, "F4": f4, "F5": f5, "F6": f6, "F7": f7, "F8": f8}


def run_drill(drill_id: str) -> dict:
    import gc
    import shutil
    tmp = Path(tempfile.mkdtemp(prefix="lab18-"))
    try:
        return RUNNERS[drill_id](tmp)
    finally:
        gc.collect()  # close the drill's database connections (Windows will not delete an open file)
        shutil.rmtree(tmp, ignore_errors=True)


def verdict(expect: dict, observed: dict) -> tuple[bool, list[str]]:
    """TODO 3. Compare a drill's expected outcome with what was observed.

    Return (passed, mismatches). For every key in `expect`, in sorted order, compare it with `observed[key]`
    (a key missing from `observed` counts as None). For the key "refused", the expectation True means
    "at least one refusal was observed" (a non-empty list), and False means none. Each mismatch is the string
    f"{key}: expected {expected!r}, got {got!r}". The drill passes when there are no mismatches.
    """
    raise NotImplementedError("TODO 3")


def run_all() -> list[tuple[dict, dict, bool, list[str]]]:
    out = []
    for drill in load_drills():
        observed = run_drill(drill["id"])
        passed, mismatches = verdict(drill["expect"], observed)
        out.append((drill, observed, passed, mismatches))
    return out
