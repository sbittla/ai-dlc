"""Memory and time for one serving model on one accelerator. TODO 1 is the memory functions; TODO 2 the timing.

The two ideas this lab rests on:

- **Memory decides how many requests can be in flight.** The weights take a fixed share of the accelerator's
  memory; the rest holds the key-value (KV) cache, which grows by a fixed number of bytes for every token of
  every request in flight.
- **Decoding is limited by memory bandwidth, not arithmetic.** Each decode step reads every weight once, plus
  the KV cache of every sequence in the batch, to produce one token per sequence. So a step costs about the
  same for one sequence as for thirty, and batching is how a server turns bandwidth into throughput. Prefill
  (reading the prompt) is the opposite: it is limited by arithmetic, at about 2 x parameters operations per
  token.
"""

from __future__ import annotations

GB = 1_000_000_000


def weights_gb(model: dict, precision: dict) -> float:
    """TODO 1a. The weights' size in GB: parameters x bytes per parameter / 1e9."""
    return model["params"] * precision["bytes_per_param"] / GB


def kv_bytes_per_token(model: dict, precision: dict) -> int:
    """TODO 1b. Bytes of KV cache per token: 2 (a key and a value) x layers x KV heads x head size x KV bytes."""
    return int(2 * model["layers"] * model["kv_heads"] * model["head_dim"] * precision["kv_bytes"])


def kv_capacity_tokens(model: dict, accel: dict, precision: dict) -> int:
    """TODO 1c. Tokens of KV cache that fit: (memory x usable share - weights) in bytes // bytes per token."""
    free = accel["memory_gb"] * accel["usable_share"] * GB - weights_gb(model, precision) * GB
    return int(free // kv_bytes_per_token(model, precision))


def prefill_s(tokens: int, model: dict, accel: dict, precision: dict) -> float:
    """TODO 2a. Seconds to read `tokens` prompt tokens: tokens x 2 x params / (TFLOPS x 1e12 x prefill speedup)."""
    return tokens * 2 * model["params"] / (accel["prefill_tflops_effective"] * 1e12 * precision["prefill_speedup"])


def decode_step_s(context_tokens: int, model: dict, accel: dict, precision: dict) -> float:
    """TODO 2b. Seconds for one decode step over a batch holding `context_tokens` tokens in all:
    the step overhead plus (weights in bytes + context_tokens x KV bytes per token) / bandwidth in bytes/s."""
    read = weights_gb(model, precision) * GB + context_tokens * kv_bytes_per_token(model, precision)
    return accel["step_overhead_ms"] / 1000 + read / (accel["bandwidth_gb_s"] * GB)
