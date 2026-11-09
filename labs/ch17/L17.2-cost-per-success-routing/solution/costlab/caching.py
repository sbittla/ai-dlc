"""Prompt caching against real arrival times: when does a cached prefix pay, and when does it not apply?

The rules modelled are a provider's, as documented in late 2026, and are assumptions to check before use:
- a prefix shorter than MIN_PREFIX tokens is never cached (no error: it is simply billed in full);
- the first call with a prefix writes it to the cache at CACHE_WRITE_MULTIPLIER x the input price;
- a call that starts within TTL_S seconds of the last call that wrote or read the same prefix, on the same
  model, reads it at 5% of the input price and restarts the clock; a later call writes it again.
Caches belong to one model, so a configuration that splits traffic between two models keeps two caches.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass

from relay.routing import CACHE_WRITE_MULTIPLIER, PRICES

from . import DATA_DIR

MIN_PREFIX = 512   # tokens; the documented minimum for the provider's current large models (assumption)
TTL_S = 300.0      # the default five-minute cache lifetime (assumption)


def week_arrivals(seed: int = 4242) -> list[float]:
    """Ticket arrival times, seconds from Monday 1 February 2027 00:00 UTC, from Lab 17.1's generated week."""
    rng = random.Random(seed)
    out = []
    with open(DATA_DIR / "source" / "tickets-per-minute.csv", newline="", encoding="utf-8") as f:
        for row in list(csv.reader(f))[1:]:
            m, n = int(row[0]), int(row[1])
            out += sorted(m * 60 + round(rng.random() * 60, 3) for _ in range(n))
    return out


@dataclass(frozen=True)
class CacheResult:
    calls: int
    writes: int
    reads: int
    uncached: int

    @property
    def hit_rate(self) -> float:
        return self.reads / self.calls


def simulate(times: list[float], prefix_tokens: int, min_prefix: int = MIN_PREFIX, ttl_s: float = TTL_S) -> CacheResult:
    """TODO 3a. Count cache writes, reads and uncached calls for one model's calls at `times` (sorted).

    If prefix_tokens < min_prefix every call is uncached. Otherwise a call is a read if it starts at most ttl_s
    after the previous call (which, read or write, restarted the entry's clock), else a write.
    """
    if prefix_tokens < min_prefix:
        return CacheResult(len(times), 0, 0, len(times))
    writes = reads = 0
    last = None
    for t in times:
        if last is not None and t - last <= ttl_s:
            reads += 1
        else:
            writes += 1
        last = t
    return CacheResult(len(times), writes, reads, 0)


def prefix_cost(r: CacheResult, prefix_tokens: int, model: str = "sim-large") -> tuple[float, float]:
    """TODO 3b. (cost without caching, cost with caching) of the prefix tokens alone, in USD.

    Without: every call pays prefix_tokens at the input price. With: uncached calls pay the input price, writes
    pay CACHE_WRITE_MULTIPLIER x the input price, reads pay the cache-read price.
    """
    p = PRICES[model]
    without = r.calls * prefix_tokens * p.input_per_mtok / 1e6
    with_cache = prefix_tokens * (r.uncached * p.input_per_mtok + r.writes * p.input_per_mtok * CACHE_WRITE_MULTIPLIER
                                  + r.reads * p.cache_read_per_mtok) / 1e6
    return without, with_cache


def split_streams(times: list[float], share_hard: float, seed: int = 77) -> tuple[list[float], list[float]]:
    """Send each arrival to the hard model with probability share_hard (the routed configuration's share)."""
    rng = random.Random(seed)
    hard, easy = [], []
    for t in times:
        (hard if rng.random() < share_hard else easy).append(t)
    return easy, hard
