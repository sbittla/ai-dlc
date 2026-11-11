"""tools/loadtest.py and perf/ (4.28.0, ADR-040): the deterministic parts of the load test, and the limiter budget.

Latency is the machine's and is not asserted here. What is asserted: the schedule, the request mix, the
percentile rule, the limiter's write transactions per request at the workload (a fitness function for
ADR-041), and that a short real run on 127.0.0.1 completes without errors.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from relay.service.directory import token_hash
from relay.service.sharedlimit import SharedRateLimiter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import loadtest  # noqa: E402

WORKLOAD = json.loads((ROOT / "perf" / "workload.json").read_text(encoding="utf-8"))
BUDGETS = json.loads((ROOT / "perf" / "budgets.json").read_text(encoding="utf-8"))


def test_the_workload_and_budgets_files():
    assert (WORKLOAD["name"], WORKLOAD["version"], WORKLOAD["test_rate_per_s"], WORKLOAD["tokens"]) == (
        "relay-api-weekday-peak", "2027.02.1", 140, 40)
    assert sum(WORKLOAD["mix"].values()) == pytest.approx(1.0, abs=0.002)
    assert (BUDGETS["service"]["p99_ms"], BUDGETS["service"]["max_limiter_transactions_per_request"],
            BUDGETS["worker"]["time_to_suggestion_p95_s"]) == (50, 0.2, 30)


def test_the_schedule_depends_only_on_its_arguments():
    arrivals = loadtest.schedule(WORKLOAD, 140, 25, seed=17)
    assert arrivals == loadtest.schedule(WORKLOAD, 140, 25, seed=17)
    steady = [a for a in arrivals if a.due_s >= 5]
    counts = {}
    for a in steady:
        counts[a.journey] = counts.get(a.journey, 0) + 1
    assert (len(arrivals), len(steady)) == (3498, 2770)
    assert counts == {"get_escalation": 300, "get_task": 2272, "get_triage_job": 134, "healthz": 61,
                      "post_triage_job": 3}


def test_nearest_rank_percentiles_by_hand():
    values = list(range(1, 101))
    assert [loadtest.percentile(values, p) for p in (50, 95, 99, 100)] == [50, 95, 99, 100]
    assert loadtest.percentile([7], 99) == 7
    with pytest.raises(ValueError):
        loadtest.percentile([], 50)


def test_requests_name_tasks_in_the_right_project():
    for i in range(400):
        method, path, headers, body = loadtest.request_for(loadtest.Arrival(i, 0.0, "get_task", 3), "t")
        _, _, pid, _, tid = path.strip("/").split("/")[:5]
        assert (int(tid) - 1000) % 2 == int(pid) - 10
    method, path, headers, body = loadtest.request_for(loadtest.Arrival(7, 0.0, "post_triage_job", 3), "t")
    assert (method, path, headers["Idempotency-Key"]) == ("POST", "/v1/triage-jobs", "lt-t-7")


def test_limiter_transactions_per_request_at_the_workload_are_within_budget(tmp_path):
    """Fitness function (ADR-041): the schedule through two leasing limiters, round-robin, one window."""
    arrivals = loadtest.schedule(WORKLOAD, WORKLOAD["test_rate_per_s"], 25, seed=17)
    db = str(tmp_path / "r.db")
    limiters = [SharedRateLimiter(db), SharedRateLimiter(db)]
    calls = 0
    for a in arrivals:
        if a.journey == "healthz":
            continue  # /healthz is not rate limited
        calls += 1
        assert limiters[a.index % 2].check(token_hash(f"lt-token-{a.token}"), 1_800_000_000.0 + a.due_s)[0]
    tx = sum(lim.transactions for lim in limiters)
    assert (calls, tx) == (3428, 376)  # 0.110 per request; 4.21.0 issued 3,428
    assert tx / calls <= BUDGETS["service"]["max_limiter_transactions_per_request"]


def test_a_short_real_run_on_loopback_completes_without_errors(tmp_path):
    out = tmp_path / "run.json"
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "loadtest.py"), "run", "--runs", "1", "--configs",
                           "lease", "--rate", "40", "--warmup", "0.5", "--duration", "2", "--servers", "1",
                           "--threads", "8", "--no-worker", "--out", str(out)], capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr[-1000:]
    run = json.loads(out.read_text(encoding="utf-8"))["runs"][0]
    assert run["errors"] == [] and set(run["status_counts"]) <= {"200", "202"}
    assert run["servers"][0]["requests"] > 0 and run["servers"][0]["limiter_transactions"] > 0
