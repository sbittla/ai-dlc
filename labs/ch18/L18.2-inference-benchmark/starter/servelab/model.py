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
    raise NotImplementedError("TODO 1a")


def kv_bytes_per_token(model: dict, precision: dict) -> int:
    """TODO 1b. Bytes of KV cache per token: 2 (a key and a value) x layers x KV heads x head size x KV bytes."""
    raise NotImplementedError("TODO 1b")


def kv_capacity_tokens(model: dict, accel: dict, precision: dict) -> int:
    """TODO 1c. Tokens of KV cache that fit: (memory x usable share - weights) in bytes // bytes per token."""
    raise NotImplementedError("TODO 1c")


def prefill_s(tokens: int, model: dict, accel: dict, precision: dict) -> float:
    """TODO 2a. Seconds to read `tokens` prompt tokens: tokens x 2 x params / (TFLOPS x 1e12 x prefill speedup)."""
    raise NotImplementedError("TODO 2a")


def decode_step_s(context_tokens: int, model: dict, accel: dict, precision: dict) -> float:
    """TODO 2b. Seconds for one decode step over a batch holding `context_tokens` tokens in all:
    the step overhead plus (weights in bytes + context_tokens x KV bytes per token) / bandwidth in bytes/s."""
    raise NotImplementedError("TODO 2b")
