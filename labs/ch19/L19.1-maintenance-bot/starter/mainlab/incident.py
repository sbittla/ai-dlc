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
    raise NotImplementedError("TODO 1: timeline")


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
    raise NotImplementedError("TODO 2: controls")
