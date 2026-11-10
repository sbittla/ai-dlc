"""Watching an AI feature and tripping its kill switch (TODO 3 in starter/).

The rule is relay-canary-v1's `ai_feature_rule`. Two cohorts of triage tickets are compared on the feature's AI
signal (here SLO-TRIAGE-QUALITY: a suggestion is bad when the person overrode it):

    cohort   tickets served WITH the feature (their workspace is in the rollout and the switch was not tripped)
    control  tickets served WITHOUT it (their workspace is not in the rollout)

Only tickets a person has confirmed by the check's time count. With n1, n2 tickets and bad shares p1, p2, the
one-sided two-proportion z statistic with a pooled share p = (b1 + b2) / (n1 + n2) is

    z = (p1 - p2) / sqrt(p (1 - p) (1/n1 + 1/n2))

It assumes the cohorts' tickets are independent and comparable: the stable hash assigns workspaces to cohorts
without regard to their tickets. Checking every five minutes is a repeated test, which raises the false-trip rate
above the single-test 1%; Lab 15.2's null scenario (A0) measures it.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field

from relay.release import FlagSet, KillStore

from .traffic import tickets

AUTOMATION = "automation:canary-ai-quality"


def z_two_proportion(bad1: int, n1: int, bad2: int, n2: int) -> float:
    """One-sided z for 'cohort 1 is worse than cohort 2'. 0.0 when the pooled share is 0 or 1."""
    p = (bad1 + bad2) / (n1 + n2)
    if p in (0.0, 1.0):
        return 0.0
    return (bad1 / n1 - bad2 / n2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))


def feature_verdict(cohort: tuple[int, int], control: tuple[int, int], rule: dict) -> tuple[bool, float, float]:
    """(trip, drop in points, z) for cohort and control given as (bad, n). Trip only when both n reach
    rule["min_events_each"], the cohort's bad share exceeds the control's by at least rule["min_drop_points"]
    points, and z >= rule["one_sided_z"]. Without enough events: (False, 0.0, 0.0)."""
    (b1, n1), (b2, n2) = cohort, control
    if n1 < rule["min_events_each"] or n2 < rule["min_events_each"]:
        return False, 0.0, 0.0
    drop = 100.0 * (b1 / n1 - b2 / n2)
    z = z_two_proportion(b1, n1, b2, n2)
    return drop >= rule["min_drop_points"] and z >= rule["one_sided_z"], drop, z


@dataclass
class Watch:
    scenario: str
    tripped_at: float | None = None
    drop: float = 0.0
    z: float = 0.0
    with_feature: int = 0             # suggestions served with the feature before the trip
    bad_with_feature: int = 0
    extra_bad: int = 0                # of those, bad only because of the feature
    first_after_trip: float | None = None
    log: list[dict] = field(default_factory=list)


def watch(scn: dict, rule: dict, seed: int = 0) -> Watch:
    """Serve the scenario's tickets in time order, deciding each one with Relay's FlagSet and a fresh KillStore.
    Every `check_every_minutes` (at 5, 10, … minutes), compute the cohorts from tickets confirmed by then and
    served before the check, and trip the switch with KillStore.trip(feature, AUTOMATION, reason, at) when
    `feature_verdict` says so. A check happens before any ticket arriving at or after its time is served."""
    feature = scn["feature"]
    doc = {"policy": "relay-flags-v1",
           "features": {feature: {"ai": True, "rollout_percent": scn["rollout_percent"], "killed": False}}}
    kills = KillStore(sqlite3.connect(":memory:"), frozenset({"sam.o"}))
    flags = FlagSet(doc, kills)
    in_rollout: dict[str, bool] = {}
    out = Watch(scn["id"])
    served: list[tuple] = []          # (ticket, with_feature)
    step = scn["check_every_minutes"]
    next_check = step

    def check(now: float) -> None:
        cohort = [t for t, w in served if w and t.confirmed <= now]
        control = [t for t, w in served if not w and not in_rollout[t.workspace] and t.confirmed <= now]
        trip, drop, z = feature_verdict((sum(t.bad_with for t in cohort), len(cohort)),
                                        (sum(t.bad_without for t in control), len(control)), rule)
        if trip:
            kills.trip(feature, AUTOMATION, f"SLO-TRIAGE-QUALITY: cohort worse by {drop:.1f} points, z={z:.2f}",
                       f"t+{now:.0f}min")
            out.tripped_at, out.drop, out.z = now, drop, z

    for t in tickets(scn, seed):
        while out.tripped_at is None and t.minute >= next_check:
            check(next_check)
            next_check += step
        if t.workspace not in in_rollout:
            in_rollout[t.workspace] = bucket_in(feature, t.workspace, scn["rollout_percent"])
        on = flags.enabled(feature, t.workspace)
        served.append((t, on))
        if on:
            out.with_feature += 1
            out.bad_with_feature += t.bad_with
            out.extra_bad += t.bad_with and not t.bad_without
        elif out.tripped_at is not None and in_rollout[t.workspace] and out.first_after_trip is None:
            out.first_after_trip = t.minute
    out.log = kills.log()
    return out


def bucket_in(feature: str, workspace: str, percent: int) -> bool:
    """Whether the workspace is in the rollout, ignoring the kill switch (provided)."""
    from relay.release.flags import bucket
    return bucket(feature, workspace) < percent


def false_trips(scn: dict, rule: dict) -> list[int]:
    """The seeds, of scn["reseeds"], on which the null scenario trips (provided)."""
    return [s for s in range(scn["reseeds"]) if watch(scn, rule, seed=s).tripped_at is not None]
