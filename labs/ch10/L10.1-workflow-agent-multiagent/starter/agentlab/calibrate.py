"""Set each design's budget from the dev split, not from a guess (provided).

Run the dev tasks under a generous calibration budget, take the successful runs, and set each limit at
1.5 times their 95th percentile, rounded up: steps to a whole step, money to the next $0.05, time to the
next minute. A successful run that needs more than that is rare on dev; a run that reaches it is far
outside what success has looked like, which is when a person should look.
"""

from __future__ import annotations

import math

from .evaluate import DESIGNS, by_design, evaluate
from .stats import percentile

HEADROOM = 1.5


def proposed_budgets() -> dict[str, dict]:
    records = evaluate("dev", calibration=True)
    out = {}
    for design in DESIGNS:
        ok = [r for r in by_design(records, design) if r.success]
        steps = percentile([r.steps for r in ok], 0.95)
        usd = percentile([r.usd for r in ok], 0.95)
        secs = percentile([r.seconds for r in ok], 0.95)
        out[design] = {
            "p95": {"steps": steps, "usd": usd, "seconds": secs, "successful_runs": len(ok)},
            "budget": {"max_steps": math.ceil(HEADROOM * steps),
                       "max_usd": math.ceil(round(HEADROOM * usd * 20, 9)) / 20,
                       "max_seconds": 60 * math.ceil(HEADROOM * secs / 60)},
        }
    return out
