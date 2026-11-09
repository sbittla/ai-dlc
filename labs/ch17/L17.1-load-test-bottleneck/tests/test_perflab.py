"""Hand-checkable tests for TODOs 1-5. Each expected value is worked out in the comment beside it."""

import pytest

from perflab.bottleneck import claim_cost, config_result, paired_ratio
from perflab.capacity import simulate
from perflab.omission import Scenario, closed_loop, corrected, open_loop
from perflab.stats import mean_interval, percentile, summarize
from perflab.workload import build_model, concurrency


# ---------------------------------------------------------------- TODO 1

def test_workload_model_on_three_hours_of_two_journeys():
    # 180 minutes; hour 1 (minutes 60-119) is busiest. Minute 90 has 120 + 0 requests: the busiest minute.
    rows = [[10, 1] for _ in range(60)] + [[30, 2] for _ in range(60)] + [[20, 0] for _ in range(60)]
    rows[90] = [120, 0]
    m = build_model(["get_task", "post_triage_job"], rows, tokens=5)
    assert m.totals == {"get_task": 3690, "post_triage_job": 178}
    assert m.peak_minute == 90 and m.peak_minute_rate == 2.0         # 120 requests / 60 s
    assert m.peak_hour == 1 and m.peak_hour_rate == pytest.approx(2008 / 3600)  # 59 x 32 + 120
    assert m.peak_hour_mix == {"get_task": round(1890 / 2008, 3), "post_triage_job": round(118 / 2008, 3)}
    assert m.test_rate == 10                                          # 2 x 2.0 = 4, rounded up to 10
    assert m.mean_rate == pytest.approx(3868 / 10800)


def test_littles_law_is_rate_times_time():
    assert concurrency(65.2, 0.002) == pytest.approx(0.1304)


# ---------------------------------------------------------------- TODO 2

def test_nearest_rank():
    v = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert [percentile(v, p) for p in (0, 10, 50, 95, 99, 100)] == [1, 1, 5, 10, 10, 10]
    with pytest.raises(ValueError):
        percentile([], 50)


def test_summary_is_in_milliseconds():
    s = summarize([3000, 1000, 2000, 4000])
    assert (s.n, s.mean_ms, s.p50_ms, s.p99_ms, s.max_ms) == (4, 2.5, 2.0, 4.0, 4.0)


def test_t_interval_by_hand():
    # mean 4, s = 2 (values 2, 4, 6), half-width 4.303 x 2 / sqrt(3) = 4.9687
    mean, low, high = mean_interval([2.0, 4.0, 6.0])
    assert mean == 4.0 and low == pytest.approx(4 - 4.96868, abs=1e-4) and high == pytest.approx(8.96868, abs=1e-4)
    with pytest.raises(ValueError):
        mean_interval([1.0])


# ---------------------------------------------------------------- TODO 3

SMALL = Scenario(duration_s=0.1, interval_ms=10.0, service_ms=1.0, stall_at_s=0.02, stall_s=0.03)


def test_open_schedule_times_every_request_from_its_due_time():
    # Due 0, 10, ..., 90 ms. The server stops 20-50 ms. Due 20 waits to 50 and finishes at 51 (31 ms);
    # due 30 at 52 (22), due 40 at 53 (13), due 50 at 54 (4).
    assert open_loop(SMALL) == [1.0, 1.0, 31.0, 22.0, 13.0, 4.0, 1.0, 1.0, 1.0, 1.0]


def test_closed_loop_records_one_slow_request_and_sends_fewer():
    # Sends at 0, 10, 20 (finishes 51), then 51 (finishes 52), 61, 71, 81, 91.
    assert closed_loop(SMALL) == [1.0, 1.0, 31.0, 1.0, 1.0, 1.0, 1.0, 1.0]


def test_correction_adds_the_samples_the_closed_loop_missed():
    assert corrected([1.0, 31.0, 1.0], 10.0) == [1.0, 31.0, 21.0, 11.0, 1.0, 1.0]


# ---------------------------------------------------------------- TODO 4

def run(config, n, lat, app, lim, tx, req):
    return {"config": config, "run": n, "latency_from_due_us": lat, "errors": [],
            "servers": [{"requests": req, "app_s": app, "limiter_s": lim, "limiter_transactions": tx}]}


RUNS = [run("exact", 1, [1000, 2000, 10000], 0.03, 0.024, 3, 3), run("lease", 1, [1000, 1000, 2000], 0.006, 0.0006, 1, 3),
        run("exact", 2, [1000, 3000, 14000], 0.03, 0.024, 3, 3), run("lease", 2, [1000, 1000, 4000], 0.006, 0.0006, 1, 3)]


def test_config_result_pools_server_counters():
    r = config_result(RUNS, "exact")
    assert (r.runs, r.requests, r.worst_max_ms) == (2, 3, 14.0)
    assert r.p99[0] == 12.0                       # per-run p99s 10 and 14 ms
    assert r.app_ms_per_request == pytest.approx(10.0)   # 0.06 s x 1000 / 6 requests
    assert r.limiter_share == pytest.approx(0.8) and r.limiter_tx_per_request == 1.0


def test_paired_ratio():
    mean, low, high = paired_ratio(RUNS, "p99_ms")    # 2/10 = 0.2 and 4/14
    assert mean == pytest.approx((0.2 + 4 / 14) / 2)


def test_the_claim_scans_without_the_index_and_searches_with_it():
    plain, indexed = claim_cost(2000, False), claim_cost(2000, True)
    assert plain.plan == ("SCAN triage_jobs",)
    assert any("USING INDEX triage_jobs_open" in line for line in indexed.plan)
    assert plain.vm_steps > 50 * max(1, indexed.vm_steps)


# ---------------------------------------------------------------- TODO 5

class FixedTriage:
    """Every call takes 2 s and returns a valid suggestion."""

    model, prompt = "fixed", "fixed"

    def classify(self, text, attempt):
        from relay.worker.triage import TriageOutcome
        return TriageOutcome('{"category": "bug", "priority": "P3", "team": "platform", "confidence": 0.9}', 2.0)


def test_one_worker_serves_arrivals_in_order():
    # Arrivals at 0, 0.5 and 1 s; one worker busy 2 s per ticket: done at 2, 4 and 6 s, so it waits 2, 3.5, 5 s.
    r = simulate([100.0, 100.5, 101.0], 1, triage=FixedTriage())
    assert (r.done, r.p50_s, r.max_s, r.max_queued) == (3, 3.5, 5.0, 2)


def test_two_workers_share_them():
    # Worker 1 takes ticket 0 at 0 (done 2); worker 2 finds the queue empty at 0, polls at 1, takes ticket 1 (done 3);
    # worker 1 takes ticket 2 at 2 (done 4). Waits 2, 2.5 and 3 s.
    r = simulate([100.0, 100.5, 101.0], 2, triage=FixedTriage())
    assert (r.p50_s, r.max_s) == (2.5, 3.0)
