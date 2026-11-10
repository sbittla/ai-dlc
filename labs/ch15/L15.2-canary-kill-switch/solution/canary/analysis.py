"""Judging one minute of a canary against the stable version (TODO 1 in starter/).

Policy: relay-canary-v1 (`vendor/config/canary.json`); targets from relay-slo-v1 (`vendor/config/slos.json`).

For a signal with target T, the bad share of a set of requests is:

    SLO-API-AVAIL    errors / requests
    SLO-API-LATENCY  slow / (requests - errors)      (the latency SLI counts only answers below 500)

and its burn rate is bad share / (1 - T), as in Chapter 16 (Equation 16.1). A burn rate of 1 spends the error
budget exactly over the SLO's period; 14.4 spends a 30-day budget's 2% in an hour.
"""

from __future__ import annotations

from .traffic import Counts


def bad_share(c: Counts, signal: str) -> float | None:
    """The bad share for `signal`, or None when there is nothing to judge (no eligible requests)."""
    if signal == "SLO-API-AVAIL":
        return c.errors / c.requests if c.requests else None
    if signal == "SLO-API-LATENCY":
        eligible = c.requests - c.errors
        return c.slow / eligible if eligible else None
    raise ValueError(f"unknown signal {signal}")


def burn(c: Counts, signal: str, target: float) -> float | None:
    share = bad_share(c, signal)
    return None if share is None else share / (1.0 - target)


def minute_verdict(stable: Counts, canary: Counts, window_canary: Counts, policy: dict, slos: dict) -> str:
    """One minute's verdict. Every burn rate here is this single minute's; the five-minute window
    (`window_canary`) only decides whether there is enough to judge.

    - "too-few"  the window holds fewer than policy["min_events_per_window"] canary requests: nothing is judged;
    - "bad:<signal>"   the first signal, in policy order, where the canary's burn rate is at least
                 policy["rollback_burn_rate"] and its bad share is above the stable version's, unless the stable
                 version also burns and the canary's bad share is at most policy["both_ratio_max"] times the
                 stable version's;
    - "both:<signal>"  otherwise, the first signal where both versions burn at the threshold or more: a shared
                 problem, usually not the release (a release can still overload a shared dependency, which is why
                 holds are limited);
    - "stable:<signal>"  the first signal where the stable version burns and the canary does not: hold, because a
                 minute in which production is unhealthy says nothing good about the canary;
    - "ok"       otherwise.
    A burn rate of None (nothing eligible) never counts as burning.
    """
    if window_canary.requests < policy["min_events_per_window"]:
        return "too-few"
    limit, ratio = policy["rollback_burn_rate"], policy["both_ratio_max"]
    rows = []
    for signal in policy["signals"]:
        target = slos[signal]["target"]
        bc, bs = burn(canary, signal, target), burn(stable, signal, target)
        rows.append((signal, bc is not None and bc >= limit, bs is not None and bs >= limit,
                     bad_share(canary, signal) or 0.0, bad_share(stable, signal) or 0.0))
    for signal, c_burns, s_burns, sc, ss in rows:
        if c_burns and sc > ss and not (s_burns and sc <= ratio * ss):
            return f"bad:{signal}"
    for signal, c_burns, s_burns, _, _ in rows:
        if c_burns and s_burns:
            return f"both:{signal}"
    for signal, c_burns, s_burns, _, _ in rows:
        if s_burns:
            return f"stable:{signal}"
    return "ok"
