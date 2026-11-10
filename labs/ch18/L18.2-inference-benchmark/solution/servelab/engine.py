"""Two serving engines on the simulated model: static and continuous batching. TODO 3 is `simulate`.

Requests come from `workload` (a seeded Poisson stream of triage-shaped requests). Both engines run on one
accelerator and use the model functions in `model.py`.

- **Static batching** waits until `static_batch` requests are queued, or `static_wait_s` has passed since the
  oldest arrived, then prefills them together and decodes until the longest one finishes. Every request in the
  batch is returned when the batch ends.
- **Continuous batching** (the scheme serving engines such as vLLM popularised) re-forms the batch at every
  decode step: finished sequences leave, and waiting requests join after a prefill, up to `max_batch` and the
  KV cache's capacity. Each request is returned when its own last token is written.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import load
from .model import decode_step_s, kv_capacity_tokens, prefill_s


@dataclass(frozen=True)
class Request:
    rid: int
    arrival: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Done:
    rid: int
    arrival: float
    first_token: float
    finished: float
    output_tokens: int


def workload(rate_per_s: float, cfg: dict | None = None) -> list[Request]:
    cfg = cfg or load("workload.json")
    rng = random.Random(f"{cfg['seed']}:{rate_per_s}")
    t, out = 0.0, []
    for rid in range(cfg["requests"]):
        t += rng.expovariate(rate_per_s)
        out.append(Request(rid, round(t, 6), rng.randint(cfg["input_tokens"]["min"], cfg["input_tokens"]["max"]),
                           rng.randint(cfg["output_tokens"]["min"], cfg["output_tokens"]["max"])))
    return out


def percentile(values: list[float], p: float) -> float:
    """Nearest rank: the smallest value with at least p% of the values at or below it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def simulate(requests: list[Request], engine: str, precision_name: str, serving: dict | None = None) -> list[Done]:
    """TODO 3. Serve `requests` with `engine` ("static" or "continuous"); return one Done per request, by rid.

    Continuous: keep a clock t, a waiting list (arrived, not admitted) and a running list.
      Repeat until every request is done:
        1. Move every request with arrival <= t into waiting, in arrival order.
        2. If nothing is running or waiting, jump t to the next arrival and go to 1.
        3. Admit from the front of waiting while len(running) < max_batch and the reserved tokens of running
           plus this request's input + output tokens fit in kv_capacity_tokens. If any were admitted,
           t += prefill_s(sum of their input tokens); each admitted request's first token is at t, with one
           output token written.
        4. A running request whose written tokens already reach its output_tokens is done at t and leaves.
        5. If anything is still running: t += decode_step_s(sum over running of input + tokens written so far);
           every running request, including those just admitted, writes one more token; a request whose
           written tokens reach its output_tokens is done at t and leaves running.
    Static: keep a clock t. Repeat until every request is done:
        1. If no request is waiting, jump t to the next arrival. The batch closes at the earlier of: the
           arrival of the static_batch-th waiting request, or the first waiting request's arrival +
           static_wait_s. t becomes max(t, that close time); the batch is the (at most static_batch) waiting
           requests that arrived by then, oldest first.
        2. t += prefill_s(sum of the batch's input tokens); every request's first token is at t.
        3. Decode max(output_tokens) - 1 steps; step k (from 1) costs decode_step_s(sum over the batch of
           input + min(output, k) tokens). Every request in the batch is done at the end of the last step.
    """
    serving = serving or load("serving.json")
    model, accel = serving["model"], serving["accelerator"]
    precision = serving["precisions"][precision_name]
    max_batch = serving["engines"]["max_batch"]
    pending = sorted(requests, key=lambda r: (r.arrival, r.rid))
    done: dict[int, Done] = {}
    if engine == "continuous":
        capacity = kv_capacity_tokens(model, accel, precision)
        t, i, waiting, running = 0.0, 0, [], []  # running: [request, written, first_token]
        while len(done) < len(pending):
            while i < len(pending) and pending[i].arrival <= t:
                waiting.append(pending[i])
                i += 1
            if not running and not waiting:
                t = pending[i].arrival
                continue
            reserved = sum(r.input_tokens + r.output_tokens for r, _, _ in running)
            admitted = []
            while waiting and len(running) + len(admitted) < max_batch:
                r = waiting[0]
                if reserved + r.input_tokens + r.output_tokens > capacity:
                    break
                reserved += r.input_tokens + r.output_tokens
                admitted.append(waiting.pop(0))
            if admitted:
                t += prefill_s(sum(r.input_tokens for r in admitted), model, accel, precision)
                for r in admitted:
                    running.append([r, 1, t])
            finished_now = [x for x in running if x[1] >= x[0].output_tokens]
            for x in finished_now:
                done[x[0].rid] = Done(x[0].rid, x[0].arrival, x[2], t, x[0].output_tokens)
            running = [x for x in running if x[1] < x[0].output_tokens]
            if running:
                t += decode_step_s(sum(x[0].input_tokens + x[1] for x in running), model, accel, precision)
                for x in running:
                    x[1] += 1
                still = []
                for x in running:
                    if x[1] >= x[0].output_tokens:
                        done[x[0].rid] = Done(x[0].rid, x[0].arrival, x[2], t, x[0].output_tokens)
                    else:
                        still.append(x)
                running = still
    elif engine == "static":
        size, wait = serving["engines"]["static_batch"], serving["engines"]["static_wait_s"]
        t, i = 0.0, 0
        while i < len(pending):
            t = max(t, pending[i].arrival)
            queued = [r for r in pending[i:] if r.arrival <= t]
            if len(queued) >= size:
                close = t
            else:
                nth = pending[i + size - 1].arrival if i + size - 1 < len(pending) else math.inf
                close = max(t, min(nth, pending[i].arrival + wait))
            t = close
            batch = [r for r in pending[i:i + size] if r.arrival <= t]
            i += len(batch)
            t += prefill_s(sum(r.input_tokens for r in batch), model, accel, precision)
            first = t
            for k in range(1, max(r.output_tokens for r in batch)):
                t += decode_step_s(sum(r.input_tokens + min(r.output_tokens, k) for r in batch), model, accel,
                                   precision)
            for r in batch:
                done[r.rid] = Done(r.rid, r.arrival, first, t, r.output_tokens)
    else:
        raise ValueError(f"unknown engine {engine!r}")
    return [done[r.rid] for r in sorted(requests, key=lambda r: r.rid)]


@dataclass(frozen=True)
class Summary:
    engine: str
    precision: str
    rate: float
    completed: int
    tokens_per_s: float
    ttft_p50: float
    ttft_p95: float
    e2e_p95: float
    meets_slo: bool


def summarize(results: list[Done], engine: str, precision: str, rate: float, slo: dict) -> Summary:
    start = min(d.arrival for d in results)
    end = max(d.finished for d in results)
    ttft = [d.first_token - d.arrival for d in results]
    e2e = [d.finished - d.arrival for d in results]
    tps = sum(d.output_tokens for d in results) / (end - start)
    ok = percentile(ttft, 95) <= slo["ttft_p95_s"] and percentile(e2e, 95) <= slo["e2e_p95_s"]
    return Summary(engine, precision, rate, len(results), round(tps, 1), round(percentile(ttft, 50), 3),
                   round(percentile(ttft, 95), 3), round(percentile(e2e, 95), 3), ok)


def sweep(engines=("static", "continuous"), precisions=("fp16", "int4")) -> list[Summary]:
    cfg = load("workload.json")
    serving = load("serving.json")
    out = []
    for precision in precisions:
        for engine in engines:
            for rate in cfg["rates_per_s"]:
                results = simulate(workload(rate, cfg), engine, precision, serving)
                out.append(summarize(results, engine, precision, rate, cfg["slo"]))
    return out
