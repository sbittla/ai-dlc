"""A guard metric after release, and the rollback it triggers (added in 4.31.0; ADR-054).

Relay's availability SLI counts a 401 as good: the server did what it promised (Chapter 16). That is right for
an availability promise and blind to a dependency that starts refusing every session. So a maintenance task type
names a **guard metric** for the behaviour its changes can break, here the share of sign-in attempts that
succeed, and the release that carries a bot's change is judged on it, canary against stable, minute by minute.

The rule is Chapter 15's rule for AI features, applied to this metric: at least `MIN_EVENTS` attempts on each
side in the window, the canary's failure share at least `MIN_POINTS` percentage points above the stable
version's, and a one-sided two-proportion z of at least 2.326. The decision is made by this deterministic code in
the delivery pipeline's rollout, never by the bot; the rollback restores the previous lock (`updates.revert`),
and the bot's outcome log records the rollback against its task type.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z_ONE_SIDED_99 = 2.326
MIN_EVENTS = 20      # attempts on each side in a window before it is judged
MIN_POINTS = 5.0     # percentage points worse before a trip


@dataclass(frozen=True)
class Window:
    minute: int
    canary_ok: int
    canary_fail: int
    stable_ok: int
    stable_fail: int


def z_worse(canary_fail: int, canary_n: int, stable_fail: int, stable_n: int) -> float:
    """One-sided two-proportion z: positive when the canary fails more often."""
    if canary_n == 0 or stable_n == 0:
        return 0.0
    p1, p2 = canary_fail / canary_n, stable_fail / stable_n
    pooled = (canary_fail + stable_fail) / (canary_n + stable_n)
    se = math.sqrt(pooled * (1 - pooled) * (1 / canary_n + 1 / stable_n))
    return (p1 - p2) / se if se > 0 else (math.inf if p1 > p2 else 0.0)


@dataclass(frozen=True)
class GuardDecision:
    minute: int | None     # the minute the guard tripped, or None
    canary_share: float
    stable_share: float
    z: float


def judge(windows: list[Window]) -> GuardDecision:
    """The first window in which the canary is worse on the guard metric; GuardDecision(None, ...) if none.

    The thresholds are this module's constants, reviewed with it; no caller sets them.
    """
    last = GuardDecision(None, 0.0, 0.0, 0.0)
    for w in windows:
        cn, sn = w.canary_ok + w.canary_fail, w.stable_ok + w.stable_fail
        if cn < MIN_EVENTS or sn < MIN_EVENTS:
            continue
        cs, ss = w.canary_fail / cn, w.stable_fail / sn
        z = z_worse(w.canary_fail, cn, w.stable_fail, sn)
        last = GuardDecision(None, cs, ss, z)
        if 100 * (cs - ss) >= MIN_POINTS and z >= Z_ONE_SIDED_99:
            return GuardDecision(w.minute, cs, ss, z)
    return last
