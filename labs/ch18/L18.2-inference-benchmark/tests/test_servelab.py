"""Hand-checkable tests for the four TODOs, on a tiny model you can work out on paper."""

import pytest

from servelab.engine import Done, Request, Summary, simulate
from servelab.model import decode_step_s, kv_bytes_per_token, kv_capacity_tokens, prefill_s, weights_gb
from servelab.plan import break_even, capacity_plan

MODEL = {"params": 1_000_000_000, "layers": 10, "kv_heads": 2, "head_dim": 50}
ACCEL = {"memory_gb": 10.0, "usable_share": 0.5, "bandwidth_gb_s": 100.0, "prefill_tflops_effective": 10.0,
         "step_overhead_ms": 1.0, "price_usd_per_hour": 2.0}
FP16 = {"bytes_per_param": 2.0, "kv_bytes": 2.0, "prefill_speedup": 1.0, "quality": 0.8}
INT4 = {"bytes_per_param": 0.5, "kv_bytes": 2.0, "prefill_speedup": 2.0, "quality": 0.7}
SERVING = {"model": MODEL, "accelerator": ACCEL, "precisions": {"fp16": FP16},
           "engines": {"max_batch": 2, "static_batch": 2, "static_wait_s": 1.0}}


def test_todo1_memory():
    assert weights_gb(MODEL, FP16) == 2.0 and weights_gb(MODEL, INT4) == 0.5
    assert kv_bytes_per_token(MODEL, FP16) == 4000  # 2 x 10 x 2 x 50 x 2
    assert kv_capacity_tokens(MODEL, ACCEL, FP16) == 750_000  # (5 GB - 2 GB) / 4000 bytes


def test_todo2_timing():
    assert prefill_s(500, MODEL, ACCEL, FP16) == pytest.approx(0.1)  # 500 x 2e9 / 1e13
    assert prefill_s(500, MODEL, ACCEL, INT4) == pytest.approx(0.05)
    assert decode_step_s(0, MODEL, ACCEL, FP16) == pytest.approx(0.021)  # 1 ms + 2 GB / 100 GB/s
    assert decode_step_s(250_000, MODEL, ACCEL, FP16) == pytest.approx(0.031)  # + 1 GB of KV cache


def test_todo3_continuous_batching_returns_each_request_when_it_is_done():
    reqs = [Request(0, 0.0, 500, 2), Request(1, 0.0, 500, 3)]
    out = simulate(reqs, "continuous", "fp16", SERVING)
    # prefill 1000 tokens: 0.2 s, first tokens at 0.2; step 1 (1002 ctx tokens) ~0.0210 s: request 0 done
    assert out[0].first_token == pytest.approx(0.2) and out[1].first_token == pytest.approx(0.2)
    step1 = decode_step_s(1002, MODEL, ACCEL, FP16)
    step2 = decode_step_s(502, MODEL, ACCEL, FP16)
    assert out[0].finished == pytest.approx(0.2 + step1)
    assert out[1].finished == pytest.approx(0.2 + step1 + step2)


def test_todo3_static_batching_waits_and_returns_the_batch_together():
    reqs = [Request(0, 0.0, 500, 2), Request(1, 0.5, 500, 3), Request(2, 0.6, 500, 1)]
    out = simulate(reqs, "static", "fp16", SERVING)
    # batch 1 closes at 0.5 (second arrival); prefill 0.2; two decode steps; both returned together
    end = 0.5 + 0.2 + decode_step_s(1002, MODEL, ACCEL, FP16) + decode_step_s(1003, MODEL, ACCEL, FP16)
    assert out[0].first_token == pytest.approx(0.7) and out[0].finished == pytest.approx(end)
    assert out[1].finished == pytest.approx(end)
    # batch 2: request 2 alone, waits until 0.6 + 1.0 or the clock, whichever is later; output 1: no decode step
    assert out[2].first_token == pytest.approx(max(end, 1.6) + 0.1) and out[2].finished == out[2].first_token
    assert isinstance(out[2], Done)


def test_todo4a_capacity_plan():
    sweep = [Summary("continuous", "fp16", 1.0, 10, 0, 0, 0, 0, True), Summary("continuous", "fp16", 4.0, 10, 0, 0, 0,
             0, True), Summary("continuous", "fp16", 8.0, 10, 0, 0, 0, 0, False)]
    volume = {"outage_peak_per_minute": 300.0, "tickets_in_replay": 3000, "replay_days": 30,
              "api_usd_per_suggestion": 0.01, "hours_per_month": 720}
    p = capacity_plan(sweep, "continuous", "fp16", volume, SERVING)
    assert (p.max_rate_meeting_slo, p.peak_rate, p.utilization_at_peak, p.replicas) == (4.0, 5.0, 1.25, 3)
    assert (p.selfhost_usd_month, p.tickets_month, p.api_usd_month) == (4320.0, 3000, 30.0)
    # one accelerator serves 4 / 5 x 3000 = 2,400 tickets a month for $1,440, more than the API's $24 for them
    assert (p.ratio, p.break_even_tickets_month, p.break_even_replicas) == (144.0, None, None)
    assert p.usd_per_ticket_full_use == 0.6  # $1,440 / 2,400 tickets


def test_todo4b_break_even_grows_the_replicas_with_the_volume():
    assert break_even(1000, 5.0, 0.01) == (1000, 2)    # 2 x $5 = $10 = 1,000 tickets x $0.01
    assert break_even(600, 5.0, 0.01) == (3000, 6)     # 5 active + 1 spare: $30 = 3,000 tickets x $0.01
    assert break_even(400, 5.0, 0.01) == (None, None)  # $5 an accelerator > $4 of API tickets it can serve
