"""Service level objectives, error budgets and multi-window burn-rate alerts (added in 4.27.0; ADR-037).

An SLO says what share of events must be good over a rolling period (30 days for Relay). The error budget
is the rest: for a 99.9% target, 0.1% of the period's events may be bad. The burn rate is how fast the
budget is being spent: the bad share in a window divided by the budget share. A burn rate of 1 spends the
budget exactly over the period; 14.4 spends 2% of a 30-day budget in one hour.

Relay pages on the multi-window, multi-burn-rate policy in Google's *Site Reliability Workbook*,
chapter "Alerting on SLOs". Each row has a long window and a short window one twelfth as long, and fires
only while both burn faster than the row's rate. The long window makes the alert significant; the short
window makes it reset soon after the problem stops.

    burn rate   long window   short window   budget spent in the long window   action
    14.4        1 hour        5 minutes      2%                               page
    6           6 hours       30 minutes     5%                               page
    1           3 days        6 hours        10%                              ticket

The input is a per-minute series of (good, total). Evaluation runs at the end of each minute over the
windows ending then. `min_events` keeps a quiet hour from paging on two failures out of three.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class BurnWindow:
    long_minutes: int
    short_minutes: int
    burn_rate: float
    action: str  # page or ticket

    def budget_spent(self, period_days: int) -> float:
        """The share of the period's budget spent in the long window at exactly this burn rate."""
        return self.burn_rate * self.long_minutes / (period_days * MINUTES_PER_DAY)


WORKBOOK_POLICY = (BurnWindow(60, 5, 14.4, "page"), BurnWindow(360, 30, 6.0, "page"),
                   BurnWindow(4320, 360, 1.0, "ticket"))


@dataclass(frozen=True)
class SLO:
    slo_id: str
    title: str
    target: float
    period_days: int = 30
    min_events: int = 0
    policy: tuple[BurnWindow, ...] = WORKBOOK_POLICY
    owner: str = ""

    @property
    def budget_ratio(self) -> float:
        return 1.0 - self.target


def burn_rate(bad: float, total: float, slo: SLO) -> float:
    """Bad share over budget share; 0 when nothing happened."""
    if total <= 0:
        return 0.0
    return (bad / total) / slo.budget_ratio


class Series:
    """Per-minute good and total counts, with prefix sums so any window costs two subtractions."""

    def __init__(self, good: list[int], total: list[int]) -> None:
        if len(good) != len(total) or any(g > t or g < 0 for g, t in zip(good, total)):
            raise ValueError("good must be between 0 and total for every minute")
        self.good, self.total = good, total
        self._g, self._t = [0], [0]
        for g, t in zip(good, total):
            self._g.append(self._g[-1] + g)
            self._t.append(self._t[-1] + t)

    def __len__(self) -> int:
        return len(self.total)

    def window(self, end: int, minutes: int) -> tuple[int, int]:
        """(bad, total) over the `minutes` minutes ending with minute `end` (inclusive)."""
        hi, lo = end + 1, max(0, end + 1 - minutes)
        total = self._t[hi] - self._t[lo]
        return total - (self._g[hi] - self._g[lo]), total


@dataclass(frozen=True)
class Episode:
    action: str
    start: int  # first minute the alert fires
    end: int    # last minute it fires
    rows: tuple[int, ...]  # indexes into the policy of the rows that fired


def firing(series: Series, slo: SLO, minute: int) -> list[int]:
    """Indexes of the policy rows firing at the end of `minute`."""
    rows = []
    for i, row in enumerate(slo.policy):
        bad_l, tot_l = series.window(minute, row.long_minutes)
        bad_s, tot_s = series.window(minute, row.short_minutes)
        if tot_l < max(1, slo.min_events):
            continue
        if burn_rate(bad_l, tot_l, slo) >= row.burn_rate and burn_rate(bad_s, tot_s, slo) >= row.burn_rate:
            rows.append(i)
    return rows


def evaluate(series: Series, slo: SLO, start: int = 0) -> list[Episode]:
    """Alert episodes per action: contiguous minutes in which at least one row with that action fires."""
    episodes: list[Episode] = []
    open_: dict[str, list] = {}
    for minute in range(start, len(series)):
        rows = firing(series, slo, minute)
        by_action: dict[str, set[int]] = {}
        for i in rows:
            by_action.setdefault(slo.policy[i].action, set()).add(i)
        for action in sorted(set(open_) | set(by_action)):
            if action in by_action:
                if action in open_:
                    open_[action][1] = minute
                    open_[action][2] |= by_action[action]
                else:
                    open_[action] = [minute, minute, set(by_action[action])]
            else:
                s, e, r = open_.pop(action)
                episodes.append(Episode(action, s, e, tuple(sorted(r))))
    for action, (s, e, r) in sorted(open_.items()):
        episodes.append(Episode(action, s, e, tuple(sorted(r))))
    return sorted(episodes, key=lambda ep: (ep.start, ep.action))


def detection_minutes(slo: SLO, row: BurnWindow, error_ratio: float) -> float:
    """Minutes from the start of a constant error ratio (from none before) until `row` fires.

    The long window reaches the threshold after burn_rate * budget_ratio * long / error_ratio minutes,
    the short one after the same with its own length; the row needs both, so the longer of the two.
    Infinite if the ratio never reaches the row's threshold.
    """
    threshold = row.burn_rate * slo.budget_ratio
    if error_ratio < threshold:
        return float("inf")
    return max(threshold * w / error_ratio for w in (row.long_minutes, row.short_minutes))


@dataclass(frozen=True)
class BudgetStatus:
    events: int
    bad: int
    allowed_bad: float
    remaining: float  # share of the budget left; negative when overspent
    burn_rate: float  # over the whole period


def budget(series: Series, slo: SLO, end: int | None = None) -> BudgetStatus:
    end = len(series) - 1 if end is None else end
    bad, total = series.window(end, slo.period_days * MINUTES_PER_DAY)
    allowed = slo.budget_ratio * total
    remaining = 1.0 - (bad / allowed) if allowed else 1.0
    return BudgetStatus(total, bad, allowed, remaining, burn_rate(bad, total, slo))


def load_slos(path: str | Path) -> dict[str, SLO]:
    """SLOs from `docs/slo/slos.json` (relay-slo-v1)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    policies = {name: tuple(BurnWindow(**row) for row in rows) for name, rows in doc["policies"].items()}
    return {s["slo_id"]: SLO(s["slo_id"], s["title"], s["target"], s.get("period_days", 30),
                             s.get("min_events", 0), policies[s["policy"]], s.get("owner", ""))
            for s in doc["slos"]}
