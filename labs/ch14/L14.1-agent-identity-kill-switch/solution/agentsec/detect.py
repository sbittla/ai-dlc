"""Detection rules over agent activity: behavioural baselines and alerts (reference solution).

The rules are Relay's own (`relay-repo/infra/detection/rules.json`, agent-detection-v1). Each keeps a
baseline per identity from a fixed baseline window, then evaluates the events after it:

- count     (DR-001) the number of matching events in the window ending at each event, inclusive.
- sum_rows  (DR-003) the sum of `rows` over matching events in the same kind of window.
            Both alert when the total exceeds max(floor, factor x the identity's baseline maximum).
- new_source (DR-002) an event from a source the identity never used in the baseline.
- any       (DR-004) any matching event.

An alert is raised at the next evaluation boundary at or after the event that triggered it (every 300 s
from midnight UTC), and repeats for the same rule and identity are suppressed for 24 hours after a
triggering event that alerted. Detection never reads an event's truth label.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class Event:
    at: datetime
    identity: str
    action: str
    resource: str
    rows: int
    source: str
    outcome: str


@dataclass(frozen=True)
class Alert:
    rule: str
    identity: str
    triggered_at: datetime
    alert_at: datetime
    value: int
    threshold: int
    index: int  # position of the triggering event in the evaluated list


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_events(path: Path) -> tuple[list[Event], list[str]]:
    """Events, and their truth labels as a separate list (for scoring only)."""
    events, truth = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        events.append(Event(parse_time(r["at"]), r["identity"], r["action"], r["resource"], r["rows"], r["source"],
                            r["outcome"]))
        truth.append(r.get("truth", ""))
    return events, truth


def load_rules(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def windowed_totals(events: list[Event], actions: list[str], window_seconds: int, use_rows: bool) -> list[tuple[int, int]]:
    """(index, total) for each event whose action is in `actions`, where total is the count (or the sum of
    rows) of that identity's matching events in the window (at - window_seconds, at], this one included."""
    windows: dict[str, deque] = defaultdict(deque)
    sums: dict[str, int] = defaultdict(int)
    out = []
    span = timedelta(seconds=window_seconds)
    for i, e in enumerate(events):
        if e.action not in actions:
            continue
        q = windows[e.identity]
        while q and q[0][0] <= e.at - span:
            _, old = q.popleft()
            sums[e.identity] -= old
        value = e.rows if use_rows else 1
        q.append((e.at, value))
        sums[e.identity] += value
        out.append((i, sums[e.identity]))
    return out


@dataclass(frozen=True)
class Baseline:
    sources: dict[str, frozenset[str]]
    maxima: dict[tuple[str, str], int]  # (rule id, identity) -> largest windowed total in the baseline

    def threshold(self, rule: dict, identity: str) -> int:
        return max(rule["floor"], rule["factor"] * self.maxima.get((rule["id"], identity), 0))


def build_baseline(events: list[Event], rules: dict) -> Baseline:
    sources: dict[str, set[str]] = defaultdict(set)
    for e in events:
        sources[e.identity].add(e.source)
    maxima: dict[tuple[str, str], int] = {}
    for rule in rules["rules"]:
        if rule["kind"] not in ("count", "sum_rows"):
            continue
        for i, total in windowed_totals(events, rule["actions"], rule["window_seconds"], rule["kind"] == "sum_rows"):
            key = (rule["id"], events[i].identity)
            maxima[key] = max(maxima.get(key, 0), total)
    return Baseline({k: frozenset(v) for k, v in sources.items()}, maxima)


def next_evaluation(t: datetime, interval_seconds: int) -> datetime:
    """The first evaluation boundary at or after t (boundaries every interval from midnight UTC)."""
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = (t - midnight).total_seconds()
    steps = -(-elapsed // interval_seconds)
    return midnight + timedelta(seconds=steps * interval_seconds)


def threshold_alerts(events: list[Event], rule: dict, baseline: Baseline, interval: int) -> list[Alert]:
    """Candidate alerts for a count or sum_rows rule: every event whose windowed total exceeds the identity's
    threshold, before de-duplication."""
    out = []
    for i, total in windowed_totals(events, rule["actions"], rule["window_seconds"], rule["kind"] == "sum_rows"):
        e = events[i]
        limit = baseline.threshold(rule, e.identity)
        if total > limit:
            out.append(Alert(rule["id"], e.identity, e.at, next_evaluation(e.at, interval), total, limit, i))
    return out


def new_source_alerts(events: list[Event], rule: dict, baseline: Baseline, interval: int) -> list[Alert]:
    """Candidate alerts for DR-002 (provided): a source outside the identity's baseline sources."""
    return [Alert(rule["id"], e.identity, e.at, next_evaluation(e.at, interval), 1, 0, i)
            for i, e in enumerate(events) if e.source not in baseline.sources.get(e.identity, frozenset())]


def any_alerts(events: list[Event], rule: dict, interval: int) -> list[Alert]:
    return [Alert(rule["id"], e.identity, e.at, next_evaluation(e.at, interval), 1, 0, i)
            for i, e in enumerate(events) if e.action in rule["actions"]]


def dedup(candidates: list[Alert], hours: int) -> list[Alert]:
    """Keep the first candidate per (rule, identity), then the next one at least `hours` after the last kept."""
    kept: list[Alert] = []
    last: dict[tuple[str, str], datetime] = {}
    for a in sorted(candidates, key=lambda a: (a.triggered_at, a.index)):
        key = (a.rule, a.identity)
        if key in last and a.triggered_at < last[key] + timedelta(hours=hours):
            continue
        last[key] = a.triggered_at
        kept.append(a)
    return kept


def evaluate(events: list[Event], rules: dict, baseline: Baseline) -> list[Alert]:
    """All alerts for `events`, ordered by alert time, then rule."""
    interval = rules["evaluation_interval_seconds"]
    out = []
    for rule in rules["rules"]:
        if rule["kind"] in ("count", "sum_rows"):
            cands = threshold_alerts(events, rule, baseline, interval)
        elif rule["kind"] == "new_source":
            cands = new_source_alerts(events, rule, baseline, interval)
        else:
            cands = any_alerts(events, rule, interval)
        out += dedup(cands, rules["dedup_hours"])
    return sorted(out, key=lambda a: (a.alert_at, a.rule, a.index))


def split(events: list[Event], truth: list[str], start: datetime, end: datetime):
    """The events (and labels) in [start, end)."""
    pairs = [(e, t) for e, t in zip(events, truth) if start <= e.at < end]
    return [e for e, _ in pairs], [t for _, t in pairs]
