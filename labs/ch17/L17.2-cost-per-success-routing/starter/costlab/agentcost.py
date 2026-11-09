"""Chapter 10's agent designs: cost per run, cost per success, the cache-write surcharge and recalibrated budgets.

Lab 10.1 priced cached input at 5% of the input price and left out the surcharge some providers charge to
write a prefix into the cache. Its runs are replayed here from their recorded token counts
(data/source/ch10-runs.jsonl, extracted by scripts/extract_ch10.py). The surcharge model is an assumption:
in a run that used caching, every input token not read from the cache is written to it, at
CACHE_WRITE_MULTIPLIER (1.25) times the input price; a run with no cached tokens wrote nothing.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from relay.routing import CACHE_WRITE_MULTIPLIER, PRICES

from . import DATA_DIR

DESIGNS = ("workflow", "single", "multi", "routed")
CH10_BUDGETS_USD = {"workflow": 0.30, "single": 0.40, "multi": 0.65, "routed": 0.55}  # Lab 10.1's designs.json
HEADROOM = 1.5


def runs() -> list[dict]:
    with open(DATA_DIR / "source" / "ch10-runs.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def nearest_rank(values: list[float], q: float) -> float:
    v = sorted(values)
    return v[max(1, math.ceil(q * len(v))) - 1]


def costs(run: dict) -> tuple[float, float, float]:
    """TODO 5a. (as Lab 10.1 priced it, with the cache-write surcharge, with no caching at all), in USD.

    Lab 10.1: (input - cached) x input price + cached x cache-read price + output x output price, per million.
    With surcharge: add (input - cached) x input price x (CACHE_WRITE_MULTIPLIER - 1) if cached > 0.
    No caching: every input token at the input price, plus output. Prices: PRICES["sim-large"].
    """
    raise NotImplementedError("TODO 5")


@dataclass(frozen=True)
class DesignCost:
    design: str
    runs: int
    successes: int
    per_run: float
    per_success: float
    per_success_surcharged: float
    per_success_uncached: float
    old_budget: float
    recalibrated_budget: float       # 1.5 x p95 of successful dev runs' surcharged cost, up to the next $0.05


def design_costs() -> list[DesignCost]:
    """TODO 5b. One row per design, held-out runs for the costs and dev calibration runs for the budget.

    per_run and per_success use the recorded `usd`; the surcharged and uncached figures use costs(). The
    recalibrated budget is math.ceil(round(1.5 x p95 x 20, 9)) / 20, with p95 the nearest-rank 95th percentile
    of the surcharged cost of the design's successful dev runs, as Lab 10.1 sets budgets.
    """
    raise NotImplementedError("TODO 5")
