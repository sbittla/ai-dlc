"""Load-test Relay's HTTP service on this machine (added in 4.28.0; ADR-040). Standard library only.

    python tools/loadtest.py run --configs exact,lease --runs 5 --out ../evidence/runs.json
    python tools/loadtest.py schedule              # the workload's deterministic schedule, summarized
    python tools/loadtest.py budgets ../evidence/runs.json   # check a run file against perf/budgets.json

What it does, per run:

1. Builds a fresh SQLite database and directory in a temporary folder: two projects, 200 tasks,
   `tokens` users with their own tokens, and 200 queued triage jobs to read back.
2. Starts `--servers` service processes, each one `wsgiref` server running the production
   application from `relay.service.wsgi.create_app` (the shared limiter included), one request at a time,
   as a gunicorn sync worker does (ADR-015). They listen on 127.0.0.1 only. The generator sends request i
   to server i mod N, a stand-in for the load balancer.
3. Starts one worker process (`python -m relay.worker --realtime`, with escalation passes), so the
   service's writes share the database with the worker's, as they do when deployed.
4. Sends the workload's requests on an OPEN schedule: arrival times are drawn in advance (Poisson, fixed
   seed), and each request is due at its time whether or not earlier ones have finished. Latency is measured
   from the time a request was DUE, so a stall that delays later requests counts against them (no
   coordinated omission). The time from when it was actually SENT is recorded too, to show the difference.
5. Discards the warm-up, keeps the steady state, and records every latency in microseconds, every status,
   and each server's own counters: requests, seconds inside the application, seconds inside the limiter,
   and the limiter's write transactions.

Each run uses the same schedule, so runs differ only by the machine's noise. With several configurations
the runs are interleaved (A, B, A, B, ...), so drift in the machine affects every configuration alike.

The numbers are this machine's. Latency depends on the CPU, the disk (every SQLite commit waits for it),
the operating system and what else is running; record them with the results (the run file does). The
deterministic parts are the schedule, the request mix and the limiter's transaction counts, which do not
depend on timing. Nothing leaves the machine: servers bind to 127.0.0.1 and the triage model is simulated.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import platform
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
WORKLOAD = ROOT / "perf" / "workload.json"
BUDGETS = ROOT / "perf" / "budgets.json"
CONFIGS = {"exact": 1, "lease": 10}  # limiter block per configuration (ADR-041): 4.21.0's exact count vs leases
STATS_PATH = "/__loadtest/stats"
STOP_PATH = "/__loadtest/stop"
TICKETS = ("The export button returns a 500 error for our whole team.",
           "How do I move a task to another project?",
           "We were charged twice this month.",
           "SSO login fails with an expired certificate.")


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the workload (deterministic)

@dataclass(frozen=True)
class Arrival:
    index: int
    due_s: float      # seconds after the run starts
    journey: str
    token: int


def schedule(workload: dict, rate: float, seconds: float, seed: int) -> list[Arrival]:
    """Poisson arrivals at `rate` per second for `seconds`, each with a journey from the mix and a token.

    One random.Random(seed) draws, per arrival: the gap (expovariate(rate)), then the journey
    (choices over the mix's journeys in sorted order, weighted by their shares), then the token
    (randrange(tokens)). The schedule depends only on its arguments, never on the machine.
    """
    rng = random.Random(seed)
    names = sorted(workload["mix"])
    weights = [workload["mix"][n] for n in names]
    out, t = [], 0.0
    while True:
        t += rng.expovariate(rate)
        if t >= seconds:
            return out
        journey = rng.choices(names, weights)[0]
        out.append(Arrival(len(out), round(t, 6), journey, rng.randrange(workload["tokens"])))


def request_for(a: Arrival, run_tag: str) -> tuple[str, str, dict, bytes | None]:
    """(method, path, headers, body) for one arrival. Paths come from the workload's journeys."""
    headers = {"Authorization": f"Bearer lt-token-{a.token}"}
    if a.journey == "get_task":
        return "GET", f"/v1/projects/{10 + a.index % 2}/tasks/{1000 + a.index % 200}", headers, None
    if a.journey == "get_escalation":
        return "GET", f"/v1/projects/10/tasks/{1000 + (a.index % 100) * 2}/escalation", headers, None
    if a.journey == "get_triage_job":
        return "GET", f"/v1/triage-jobs/{1 + a.index % 200}", headers, None
    if a.journey == "post_triage_job":
        body = json.dumps({"text": TICKETS[a.index % len(TICKETS)] + f" (ref {run_tag}-{a.index})"}).encode()
        headers.update({"Content-Type": "application/json", "Idempotency-Key": f"lt-{run_tag}-{a.index}"})
        return "POST", "/v1/triage-jobs", headers, body
    if a.journey == "healthz":
        return "GET", "/healthz", {}, None
    raise ValueError(f"unknown journey {a.journey!r}")


def percentile(sorted_values: list[int], p: float) -> int:
    """Nearest-rank percentile: the smallest value with at least p% of the values at or below it."""
    if not sorted_values:
        raise ValueError("no values")
    rank = max(1, math.ceil(p / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


# ------------------------------------------------------------------ fixture

def build_fixture(folder: Path, tokens: int) -> tuple[str, str]:
    """A database and a directory file for one run. Returns (db path, directory path)."""
    sys.path.insert(0, str(SRC))
    from datetime import date

    from relay.models import Task
    from relay.service.directory import token_hash
    from relay.store import TaskStore
    from relay.worker import TriageQueue

    db = str(folder / "relay.db")
    store = TaskStore(db)
    for i in range(200):
        store.add(Task(1000 + i, 10 + i % 2, f"Load-test task {i}", "open", date(2027, 3, 1), None))
    store.conn.close()
    queue = TriageQueue(db)
    for i in range(200):
        queue.enqueue("ws-load", f"seed-job-{i:04d}", TICKETS[i % len(TICKETS)], 1_700_000_000.0)
    queue.conn.close()
    users = [{"id": 100 + i, "email": f"u{i}@example.com", "name": f"User {i}",
              "role": ("Admin", "Member")[i % 2], "tz": "UTC", "token_sha256": token_hash(f"lt-token-{i}")}
             for i in range(tokens)]
    directory = folder / "directory.json"
    directory.write_text(json.dumps({"workspace": "ws-load", "users": users,
                                     "projects": [{"id": 10, "name": "Rotterdam"}, {"id": 11, "name": "Hamburg"}]}),
                         encoding="utf-8")
    return db, str(directory)


# ------------------------------------------------------------------ one server process

def serve(db: str, directory: str, block: int, window_base: float) -> None:
    """Run the production app under wsgiref on 127.0.0.1, one request at a time, and print the port."""
    sys.path.insert(0, str(SRC))
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

    from relay.service.sharedlimit import SharedRateLimiter
    from relay.service.wsgi import create_app

    app = create_app({"RELAY_DB_PATH": db, "RELAY_DIRECTORY_FILE": directory,
                      "RELAY_LINK_BASE": "https://relay.example/ws-load"})
    limiter = SharedRateLimiter(db, block=block)
    started = time.time()
    app.clock = lambda: window_base + (time.time() - started)  # windows start with the run, so counts repeat
    stats = {"requests": 0, "app_s": 0.0, "limiter_s": 0.0}

    class TimedLimiter:
        def check(self, key: str, now: float):
            t0 = time.perf_counter()
            try:
                return limiter.check(key, now)
            finally:
                stats["limiter_s"] += time.perf_counter() - t0

    app.limiter = TimedLimiter()
    stop = {"now": False}

    def wrapped(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in (STATS_PATH, STOP_PATH):
            stop["now"] = path == STOP_PATH
            body = json.dumps({**stats, "limiter_transactions": limiter.transactions}).encode()
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
            return [body]
        t0 = time.perf_counter()
        try:
            return app(environ, start_response)
        finally:
            stats["requests"] += 1
            stats["app_s"] += time.perf_counter() - t0

    class Server(WSGIServer):
        request_queue_size = 512  # wsgiref's default backlog of 5 refuses bursts; gunicorn's default is 2048

    class Quiet(WSGIRequestHandler):
        def log_message(self, format, *args):
            pass

    httpd = make_server("127.0.0.1", 0, wrapped, server_class=Server, handler_class=Quiet)
    sys.stdout.write(f"{httpd.server_port}\n")
    sys.stdout.flush()
    while not stop["now"]:
        httpd.handle_request()
    httpd.server_close()


# ------------------------------------------------------------------ the generator

def call(port: int, method: str, path: str, headers: dict, body: bytes | None) -> int:
    # No socket timeout: on Windows a socket with a timeout waits in steps of the system timer (about 15.6 ms),
    # which added that much to every request in this tool's first version. A run-level deadline replaces it.
    conn = http.client.HTTPConnection("127.0.0.1", port)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        return resp.status
    except OSError:
        return 0  # connection refused, reset or timed out: counted as an error
    finally:
        conn.close()


def drive(arrivals: list[Arrival], ports: list[int], threads: int, run_tag: str) -> list[tuple]:
    """Send each arrival at its due time from a pool of threads. Returns (index, due, sent, done, status)."""
    results: list[tuple | None] = [None] * len(arrivals)
    lock = threading.Lock()
    nxt = [0]
    t0 = time.perf_counter() + 0.5

    def worker() -> None:
        while True:
            with lock:
                i = nxt[0]
                nxt[0] += 1
            if i >= len(arrivals):
                return
            a = arrivals[i]
            due = t0 + a.due_s
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            sent = time.perf_counter()
            status = call(ports[a.index % len(ports)], *request_for(a, run_tag))
            done = time.perf_counter()
            results[i] = (a.index, due - t0, sent - t0, done - t0, status)

    pool = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
    for th in pool:
        th.start()
    deadline = time.perf_counter() + arrivals[-1].due_s + 120 if arrivals else time.perf_counter()
    for th in pool:
        th.join(max(0.0, deadline - time.perf_counter()))
    # A request still unanswered at the deadline is an error, timed at the deadline.
    return [r if r is not None else (a.index, a.due_s, a.due_s, deadline - t0, 0) for a, r in zip(arrivals, results)]


def http_json(port: int, path: str) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request("GET", path)
    data = json.loads(conn.getresponse().read())
    conn.close()
    return data


def one_run(config: str, run_no: int, args, workload: dict, arrivals: list[Arrival]) -> dict:
    folder = Path(tempfile.mkdtemp(prefix="relay-loadtest-"))
    procs: list[subprocess.Popen] = []
    env = dict(os.environ, PYTHONPATH=str(SRC))
    try:
        db, directory = build_fixture(folder, workload["tokens"])
        base = 1_800_000_000.0  # a multiple of 60: the first window starts with the run
        for _ in range(args.servers):
            procs.append(subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--db", db,
                                           "--directory", directory, "--block", str(CONFIGS[config]),
                                           "--window-base", str(base)],
                                          stdout=subprocess.PIPE, text=True, env=env))
        ports = [int(p.stdout.readline()) for p in procs]
        worker = None
        if args.worker:
            worker = subprocess.Popen([sys.executable, "-m", "relay.worker", "--db", db, "--realtime",
                                       "--directory", directory, "--link-base", "https://relay.example/ws-load",
                                       "--poll", "1"], stdout=subprocess.DEVNULL, env=env)
        results = drive(arrivals, ports, args.threads, f"{config}{run_no}")
        stats = [http_json(port, STOP_PATH) for port in ports]
        if worker is not None:
            worker.terminate()
            worker.wait(timeout=30)
        for p in procs:
            p.wait(timeout=30)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
        shutil.rmtree(folder, ignore_errors=True)
    steady = [r for r in results if r[1] >= args.warmup]
    return {
        "config": config, "run": run_no, "block": CONFIGS[config],
        "latency_from_due_us": [round((r[3] - r[1]) * 1e6) for r in steady],
        "latency_from_sent_us": [round((r[3] - r[2]) * 1e6) for r in steady],
        "first_index": steady[0][0] if steady else None,
        "status_counts": {str(k): v for k, v in sorted(_count(r[4] for r in steady).items())},
        "errors": [r[0] for r in steady if r[4] == 0 or r[4] >= 500],
        "servers": stats,
    }


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def error_share(run: dict) -> float:
    return len(run["errors"]) / len(run["latency_from_due_us"])


def environment() -> dict:
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "cpus": os.cpu_count(), "sqlite": sqlite3.sqlite_version,
            "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def run(args) -> int:
    workload = load_json(WORKLOAD)
    rate = args.rate or workload["test_rate_per_s"]
    arrivals = schedule(workload, rate, args.warmup + args.duration, args.seed)
    configs = args.configs.split(",")
    runs = []
    for run_no in range(1, args.runs + 1):
        for config in configs:
            sys.stderr.write(f"run {run_no} {config} ...\n")
            runs.append(one_run(config, run_no, args, workload, arrivals))
    out = {"tool": "relay tools/loadtest.py 4.28.0", "workload": workload["name"], "version": workload["version"],
           "rate_per_s": rate, "warmup_s": args.warmup, "duration_s": args.duration, "seed": args.seed,
           "servers": args.servers, "threads": args.threads, "worker": args.worker, "arrivals": len(arrivals),
           "environment": environment(), "runs": runs}
    text = json.dumps(out, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    for r in runs:
        lat = sorted(r["latency_from_due_us"])
        sys.stdout.write(f"{r['config']:>6} run {r['run']}: n={len(lat)} p50={percentile(lat, 50) / 1000:.2f} ms "
                         f"p95={percentile(lat, 95) / 1000:.2f} ms p99={percentile(lat, 99) / 1000:.2f} ms "
                         f"errors={len(r['errors'])}\n")
    return 0


def check_budgets(path: str) -> int:
    """Exit 1 if any run in the file breaks a budget in perf/budgets.json (latency budgets are advisory here)."""
    budgets = load_json(BUDGETS)["service"]
    data = load_json(Path(path))
    failed = 0
    for r in data["runs"]:
        lat = sorted(r["latency_from_due_us"])
        p99_ms = percentile(lat, 99) / 1000
        errors = error_share(r)
        tx = sum(s["limiter_transactions"] for s in r["servers"]) / sum(s["requests"] for s in r["servers"])
        problems = []
        if p99_ms > budgets["p99_ms"]:
            problems.append(f"p99 {p99_ms:.1f} ms > {budgets['p99_ms']} ms")
        if errors > budgets["max_error_share"]:
            problems.append(f"errors {errors:.2%}")
        if tx > budgets["max_limiter_transactions_per_request"]:
            problems.append(f"limiter transactions per request {tx:.3f} > "
                            f"{budgets['max_limiter_transactions_per_request']}")
        sys.stdout.write(f"{r['config']} run {r['run']}: {'; '.join(problems) or 'within budget'}\n")
        failed += bool(problems)
    return 1 if failed else 0


def summarize_schedule(args) -> int:
    workload = load_json(WORKLOAD)
    rate = args.rate or workload["test_rate_per_s"]
    arrivals = schedule(workload, rate, args.warmup + args.duration, args.seed)
    steady = [a for a in arrivals if a.due_s >= args.warmup]
    counts: dict[str, int] = {}
    for a in steady:
        counts[a.journey] = counts.get(a.journey, 0) + 1
    sys.stdout.write(f"{workload['name']} {workload['version']}: {len(arrivals)} arrivals at {rate:g}/s over "
                     f"{args.warmup + args.duration:g} s (seed {args.seed}); steady state {len(steady)}\n")
    for name in sorted(counts):
        sys.stdout.write(f"  {name}: {counts[name]}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python tools/loadtest.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "schedule"):
        p = sub.add_parser(name)
        p.add_argument("--rate", type=float, default=None, help="arrivals per second (default: the workload's)")
        p.add_argument("--warmup", type=float, default=5.0)
        p.add_argument("--duration", type=float, default=20.0)
        p.add_argument("--seed", type=int, default=17)
        if name == "run":
            p.add_argument("--configs", default="exact,lease")
            p.add_argument("--runs", type=int, default=5)
            p.add_argument("--servers", type=int, default=2)
            p.add_argument("--threads", type=int, default=64)
            p.add_argument("--no-worker", dest="worker", action="store_false")
            p.add_argument("--out", default=None)
    b = sub.add_parser("budgets")
    b.add_argument("path")
    s = sub.add_parser("serve")
    s.add_argument("--db", required=True)
    s.add_argument("--directory", required=True)
    s.add_argument("--block", type=int, required=True)
    s.add_argument("--window-base", type=float, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        serve(args.db, args.directory, args.block, args.window_base)
        return 0
    if args.cmd == "budgets":
        return check_budgets(args.path)
    if args.cmd == "schedule":
        return summarize_schedule(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
