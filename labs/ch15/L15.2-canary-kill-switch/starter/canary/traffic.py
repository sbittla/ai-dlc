"""Deterministic draws for the scenarios (provided).

`minute_counts` gives the stable and canary versions' requests, server errors and slow answers for one minute at
a given canary share. `tickets` gives the triage tickets of an AI scenario, each with its workspace, its time,
when a person confirmed it, and whether its suggestion was bad with the feature and without it (both drawn, so
the kill switch's effect is the difference). Seeds come from SHA-256 of the scenario, minute and version, so
the draws do not depend on the order of calls or on the platform.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Counts:
    requests: int = 0
    errors: int = 0      # status 500 and above
    slow: int = 0        # status below 500, over 250 ms

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(self.requests + other.requests, self.errors + other.errors, self.slow + other.slow)


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()[:16], 16))


def _probs(scn: dict, version: str, minute: int) -> tuple[float, float]:
    p = scn[version]
    err, slow = p["error_p"], p["slow_p"]
    inc = scn.get("incident")
    if inc and inc["from"] <= minute <= inc["to"] and version in inc["versions"]:
        err = inc["error_p"]
    return err, slow


def _draw(scn: dict, version: str, minute: int, n: int) -> Counts:
    rng = _rng(scn["id"], minute, version)
    err_p, slow_p = _probs(scn, version, minute)
    errors = slow = 0
    for _ in range(n):
        r = rng.random()
        if r < err_p:
            errors += 1
        elif r < err_p + slow_p:
            slow += 1
    return Counts(n, errors, slow)


def minute_counts(scn: dict, minute: int, share: float) -> tuple[Counts, Counts]:
    """(stable, canary) for one minute when the canary takes `share` of requests (0.0 to 1.0)."""
    total = scn["rate_per_minute"]
    to_canary = round(total * share)
    return _draw(scn, "stable", minute, total - to_canary), _draw(scn, "canary", minute, to_canary)


@dataclass(frozen=True)
class Ticket:
    n: int
    minute: float           # minutes after the scenario's start
    workspace: str
    confirmed: float        # minute a person confirmed or overrode the suggestion
    bad_with: bool          # the suggestion was overridden, with the feature on
    bad_without: bool       # the same ticket on the stable route


def tickets(scn: dict, seed: int = 0) -> list[Ticket]:
    rng = _rng(scn["id"], "tickets", seed)
    out, t, n = [], 0.0, 0
    horizon = scn["hours"] * 60
    rate = scn["tickets_per_hour"] / 60.0
    while True:
        t += rng.expovariate(rate)
        if t >= horizon:
            return out
        n += 1
        ws = f"ws-{rng.randrange(scn['workspaces']):04d}"
        confirmed = t + rng.expovariate(1.0 / scn["confirm_mean_minutes"])
        u = rng.random()
        out.append(Ticket(n, round(t, 3), ws, round(confirmed, 3), u < scn["bad_p"]["feature"],
                          u < scn["bad_p"]["control"]))
