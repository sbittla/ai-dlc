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
    raise NotImplementedError("TODO 3")


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
