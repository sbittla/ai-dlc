"""Detection rules evaluated in the telemetry pipeline (added in 4.27.0; ADR-038).

Chapter 14 wrote agent-detection-v1 (`infra/detection/rules.json`, DR-001 to DR-004) and evaluated it
offline in Lab 14.1. This module is the deployed evaluator. It runs every 5 minutes as a scheduled task
(`infra/monitoring/`), reads the audit trail of agent actions, verifies the trail's chain before trusting
it, and evaluates the rules with a 28-day baseline per identity. 4.27.0 adds a second rule set,
relay-service-detection-v1 (`infra/detection/service-rules.json`, SD-001 to SD-003), over the security
events the service and the sign-in path emit: authentication failures and successes, by network.

Rule kinds:

- count     matching events in the window (at - window, at] per group, against max(floor, factor x the
            group's baseline maximum). The group is the identity unless the rule says `group_by`.
- sum_rows  the same with the sum of `rows`.
- distinct  distinct values of `field` per group in the window, against the same kind of threshold.
- new_source an event from a source the identity never used in the baseline.
- after_failures a success from a group that had at least `floor` failures in the window before it.
- any       any matching event.

An alert is raised at the first evaluation boundary at or after its triggering event, and repeats for the
same rule and group are suppressed for `dedup_hours`. Alerts carry evidence references (`trail:<seq>`,
`event:<index>`) so a person, or an assistant, can cite exactly what fired.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path

from ..audit import trail as _trail


@dataclass(frozen=True)
class Event:
    at: datetime
    identity: str
    action: str
    resource: str
    rows: int
    source: str
    outcome: str
    credential: str = ""
    ref: str = ""


@dataclass(frozen=True)
class Alert:
    rule: str
    group: str
    triggered_at: datetime
    alert_at: datetime
    value: int
    threshold: int
    severity: str
    evidence: tuple[str, ...]


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def from_trail(records: list[dict]) -> list[Event]:
    """Events from audit-trail records (relay.audit.trail): identity is the agent, rows from the detail."""
    return [Event(parse_time(r["at"]), r.get("agent_id") or "-", r["action"], r["resource"],
                  int((r.get("detail") or {}).get("rows", 0)), r["source"], r["outcome"], r.get("credential") or "",
                  f"trail:{r['seq']}") for r in records]


def from_security_events(records: list[dict]) -> list[Event]:
    """Events from the security event stream: {at, event, network, credential, outcome, route}."""
    return [Event(parse_time(r["at"]), r.get("credential") or "-", r["event"], r.get("route", ""), 0,
                  r["network"], r.get("outcome", ""), r.get("credential") or "", f"event:{i}")
            for i, r in enumerate(records)]


def trail_records(lines: list[str]) -> list[dict]:
    """Audit-trail records from JSON lines: raw trail lines, or OTLP log lines whose bodies are trail lines."""
    out = []
    for line in lines:
        if not line.strip():
            continue
        doc = json.loads(line)
        if "resourceLogs" not in doc:
            out.append(doc)
            continue
        for rl in doc["resourceLogs"]:
            for sl in rl["scopeLogs"]:
                out += [json.loads(rec["body"]["stringValue"]) for rec in sl["logRecords"]]
    return out


def security_events_from_otlp(lines: list[str]) -> list[dict]:
    """The security events in OTLP log export lines (written by relay.service.telemetry), in time order."""
    out = []
    for line in lines:
        if not line.strip():
            continue
        for rl in json.loads(line).get("resourceLogs", []):
            for sl in rl["scopeLogs"]:
                for rec in sl["logRecords"]:
                    a = {kv["key"]: next(iter(kv["value"].values())) for kv in rec["attributes"]}
                    if "relay.security.event" not in a:
                        continue
                    at = datetime.fromtimestamp(int(rec["timeUnixNano"]) / 1e9, tz=timezone.utc)
                    out.append({"at": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "event": a["relay.security.event"],
                                "network": a.get("relay.client.network", "unknown"),
                                "credential": a.get("relay.credential.fingerprint", ""),
                                "route": a.get("http.route", ""), "outcome": str(a.get("http.response.status_code"))})
    return sorted(out, key=lambda r: r["at"])


def verified_trail(records: list[dict], anchor: tuple[int, str] | None = None) -> tuple[bool, str]:
    """Verify the chain (and an anchor) before any rule reads the trail. (ok, reason)."""
    result = _trail.verify(records, anchor)
    return result.ok, "" if result.ok else f"{result.problem} at record {result.seq}"


def load_rules(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _group(rule: dict, e: Event) -> str:
    return {"identity": e.identity, "source": e.source, "all": "*"}[rule.get("group_by", "identity")]


MAX_EVIDENCE = 10  # an alert cites at most the last ten events in its window


def windowed(events: list[Event], rule: dict) -> list[tuple[int, int, tuple[str, ...]]]:
    """(index, value, evidence) for each matching event: the count, row sum or distinct count in its group's
    window, kept incrementally, and the references of the last MAX_EVIDENCE events in that window."""
    span = timedelta(seconds=rule["window_seconds"])
    queues: dict[str, deque] = defaultdict(deque)
    sums: dict[str, int] = defaultdict(int)
    distinct: dict[str, Counter] = defaultdict(Counter)
    field = rule.get("field", "credential")
    out = []
    for i, e in enumerate(events):
        if e.action not in rule["actions"]:
            continue
        g = _group(rule, e)
        q = queues[g]
        while q and q[0][0] <= e.at - span:
            _, old, key, _ = q.popleft()
            sums[g] -= old
            distinct[g][key] -= 1
            if not distinct[g][key]:
                del distinct[g][key]
        value = e.rows if rule["kind"] == "sum_rows" else 1
        key = getattr(e, field)
        q.append((e.at, value, key, e.ref))
        sums[g] += value
        distinct[g][key] += 1
        tail = tuple(reversed([item[3] for item in islice(reversed(q), MAX_EVIDENCE)]))
        out.append((i, len(distinct[g]) if rule["kind"] == "distinct" else sums[g], tail))
    return out


@dataclass(frozen=True)
class Baseline:
    sources: dict[str, frozenset[str]]
    maxima: dict[tuple[str, str], int]

    def threshold(self, rule: dict, group: str) -> int:
        return max(rule["floor"], int(rule["factor"] * self.maxima.get((rule["id"], group), 0)))


def build_baseline(events: list[Event], ruleset: dict) -> Baseline:
    sources: dict[str, set[str]] = defaultdict(set)
    for e in events:
        sources[e.identity].add(e.source)
    maxima: dict[tuple[str, str], int] = {}
    for rule in ruleset["rules"]:
        if rule["kind"] in ("count", "sum_rows", "distinct"):
            for i, value, _ in windowed(events, rule):
                key = (rule["id"], _group(rule, events[i]))
                maxima[key] = max(maxima.get(key, 0), value)
    return Baseline({k: frozenset(v) for k, v in sources.items()}, maxima)


def next_evaluation(t: datetime, interval_seconds: int) -> datetime:
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    steps = -(-(t - midnight).total_seconds() // interval_seconds)
    return midnight + timedelta(seconds=steps * interval_seconds)


def _candidates(events: list[Event], rule: dict, baseline: Baseline, interval: int) -> list[Alert]:
    sev, out = rule["severity"], []
    kind = rule["kind"]
    if kind in ("count", "sum_rows", "distinct"):
        for i, value, refs in windowed(events, rule):
            e = events[i]
            group = _group(rule, e)
            limit = baseline.threshold(rule, group)
            if value > limit:
                out.append(Alert(rule["id"], group, e.at, next_evaluation(e.at, interval), value, limit, sev, refs))
    elif kind == "new_source":
        for e in events:
            if e.source not in baseline.sources.get(e.identity, frozenset()):
                out.append(Alert(rule["id"], e.identity, e.at, next_evaluation(e.at, interval), 1, 0, sev, (e.ref,)))
    elif kind == "after_failures":
        span = timedelta(seconds=rule["window_seconds"])
        failures: dict[str, deque] = defaultdict(deque)
        for e in events:
            g = _group(rule, e)
            q = failures[g]
            while q and q[0].at <= e.at - span:
                q.popleft()
            if e.action == rule["failure_action"]:
                q.append(e)
            elif e.action in rule["actions"] and len(q) >= rule["floor"]:
                out.append(Alert(rule["id"], g, e.at, next_evaluation(e.at, interval), len(q), rule["floor"], sev,
                                 (q[0].ref, e.ref)))
    elif kind == "any":
        out = [Alert(rule["id"], e.identity, e.at, next_evaluation(e.at, interval), 1, 0, sev, (e.ref,))
               for e in events if e.action in rule["actions"]]
    else:
        raise ValueError(f"unknown rule kind {kind}")
    return out


def dedup(candidates: list[Alert], hours: int) -> list[Alert]:
    kept, last = [], {}
    for a in sorted(candidates, key=lambda a: (a.triggered_at, a.evidence)):
        key = (a.rule, a.group)
        if key in last and a.triggered_at < last[key] + timedelta(hours=hours):
            continue
        last[key] = a.triggered_at
        kept.append(a)
    return kept


def evaluate(events: list[Event], ruleset: dict, baseline: Baseline) -> list[Alert]:
    """Every alert for `events` (sorted by time), ordered by alert time, then rule."""
    interval = ruleset["evaluation_interval_seconds"]
    out = []
    for rule in ruleset["rules"]:
        out += dedup(_candidates(events, rule, baseline, interval), ruleset["dedup_hours"])
    return sorted(out, key=lambda a: (a.alert_at, a.rule, a.triggered_at))
