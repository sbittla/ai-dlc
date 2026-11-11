"""The 20 May 2027 lockout (composite), and what Chapter 19's controls do with the same update.

TODO 1 `timeline`: the incident's numbers from the per-minute sign-in record.
TODO 2 `controls`: the same update under relay-maintenance-policy-v1: the plan, the sandbox checks, the guard.
"""

from __future__ import annotations

from dataclasses import dataclass

from relay.maintenance import judge, plan_update
from relay.maintenance.evidence import defaults_script, sandbox_check
from relay.maintenance.guard import Window
from relay.maintenance.updates import Mirror

from .world import POLICY, load, read, webapp_files


@dataclass(frozen=True)
class Timeline:
    first_affected: str
    full_from: str
    restored: str
    affected_minutes: int
    full_minutes: int
    failures_affected: int
    baseline_failure_pct: float
    accounts_during_full: int
    page_to_restore_minutes: int


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def timeline(data: dict) -> Timeline:
    """TODO 1. From `data["minutes"]` (one record per minute, in order):

    - first_affected: the first minute with new_version_share > 0; full_from: the first with 100;
      restored: the first minute after full_from whose share is 0;
    - affected_minutes: minutes from first_affected up to (not including) restored; full_minutes likewise from
      full_from;
    - failures_affected: the sum of `failures` over the affected minutes;
    - baseline_failure_pct: failures / attempts over the minutes before first_affected, in percent, 1 decimal;
    - accounts_during_full: the sum of `new_accounts` over the full minutes;
    - page_to_restore_minutes: from the SD-001 page (the event whose text starts "SD-001") to `restored`.
    """
    rows = data["minutes"]
    first = next(r["minute"] for r in rows if r["new_version_share"] > 0)
    full = next(r["minute"] for r in rows if r["new_version_share"] == 100)
    restored = next(r["minute"] for r in rows if r["minute"] > full and r["new_version_share"] == 0)
    affected = [r for r in rows if first <= r["minute"] < restored]
    whole = [r for r in rows if full <= r["minute"] < restored]
    before = [r for r in rows if r["minute"] < first]
    page = next(e["at"] for e in data["events"] if e["what"].startswith("SD-001"))
    return Timeline(first, full, restored, len(affected), len(whole), sum(r["failures"] for r in affected),
                    round(100 * sum(r["failures"] for r in before) / sum(r["attempts"] for r in before), 1),
                    sum(r["new_accounts"] for r in whole), _minutes(restored) - _minutes(page))


@dataclass(frozen=True)
class Controls:
    plan: object
    app_tests: object
    round_trip: object
    defaults: object
    guard_minute: str | None
    guard_canary_pct: float
    guard_stable_pct: float
    canary_failures_before_trip: int


def controls(data: dict) -> Controls:
    """TODO 2. The same update on 20 May under Chapter 19's controls.

    1. `plan_update("sessionkeel", <the 2.4.1 lock>, Mirror(<mirror.json>), "2027-05-20", POLICY.sensitive_packages)`.
    2. In the sandbox, against `webapp_files("2.5.0")`: the app's tests (`webapp/app_tests.py`), the round trip
       added after the incident (`webapp/round_trip.py`) and the pinned defaults
       (`defaults_script("sessionkeel", <webapp/pinned-defaults.json>)`), each with `sandbox_check`.
    3. The guard on the 5% stage: one `Window` per minute whose new_version_share is 5, numbered from 1, with the
       new version as canary and the old as stable; `judge(windows)`. guard_minute is the trip minute's clock time
       (the window's `minute` field), and canary_failures_before_trip sums the new version's failures up to and
       including that minute.
    """
    mirror = Mirror(load("mirror.json"))
    plan = plan_update("sessionkeel", read("webapp/requirements-2.4.1.lock"), mirror, "2027-05-20",
                       POLICY.sensitive_packages)
    files = webapp_files("2.5.0")
    app = sandbox_check("app-tests", files, read("webapp/app_tests.py"))
    trip = sandbox_check("round-trip", files, read("webapp/round_trip.py"))
    defaults = sandbox_check("pinned-defaults", files,
                             defaults_script("sessionkeel", load("webapp/pinned-defaults.json")))
    stage = [r for r in data["minutes"] if r["new_version_share"] == 5]
    windows = [Window(i, r["new_version_attempts"] - r["new_version_failures"], r["new_version_failures"],
                      r["old_version_attempts"] - r["old_version_failures"], r["old_version_failures"])
               for i, r in enumerate(stage, 1)]
    d = judge(windows)
    minute = stage[d.minute - 1]["minute"] if d.minute else None
    before = sum(r["new_version_failures"] for r in stage[:d.minute]) if d.minute else 0
    return Controls(plan, app, trip, defaults, minute, round(100 * d.canary_share, 1), round(100 * d.stable_share, 1),
                    before)
