"""The monitor: turns collected telemetry into alerts, and alerts into pages (added in 4.27.0; ADR-038).

Inputs, as the gateway collector writes them (`infra/monitoring/collector.yaml`): OTLP metric and log export
lines, and the audit trail of agent actions as JSON lines. Each `tick` evaluates

- the SLOs in `docs/slo/slos.json` with their burn-rate policies, over per-minute SLI counts rebuilt from the
  cumulative `relay.sli.events` counter;
- the operational rules in `infra/monitoring/alerts.json` over a snapshot of values;
- agent-detection-v1 over the trail, after verifying its chain (a broken chain is itself an alert,
  TRAIL-TAMPER), and relay-service-detection-v1 over the security events;

and hands every new alert to `alerting.Router`, which pages, opens a ticket or trips a kill switch. The
monitor makes no network call. Its `send` is given to it: in production `relay.service.pager.PagerClient`, in
tests and labs `alerting.Pager`.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import detection, semconv
from .alerting import AlertRecord, Router, from_detection, from_episode, operational_alerts
from .slo import Series, evaluate


def _attrs(kvs: list[dict]) -> dict:
    out = {}
    for kv in kvs:
        v = kv["value"]
        out[kv["key"]] = next(iter(v.values()))
    return out


def minute_of(ns: int) -> datetime:
    t = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    return t.replace(second=0, microsecond=0)


def sli_minutes_from_otlp(lines: list[str]) -> dict[str, dict[datetime, list[int]]]:
    """Per-minute [good, total] for each SLO, from cumulative `relay.sli.events` points in export order."""
    last: dict[tuple, int] = {}
    out: dict[str, dict[datetime, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for line in lines:
        if not line.strip():
            continue
        for rm in json.loads(line).get("resourceMetrics", []):
            resource = tuple(sorted(_attrs(rm["resource"]["attributes"]).items()))
            for sm in rm["scopeMetrics"]:
                for metric in sm["metrics"]:
                    if metric["name"] != "relay.sli.events":
                        continue
                    for p in metric["sum"]["dataPoints"]:
                        a = _attrs(p["attributes"])
                        key = (resource, p["startTimeUnixNano"], a[semconv.RELAY_SLO_ID], a[semconv.RELAY_SLI_GOOD])
                        value = int(p["asInt"])
                        delta = value - last.get(key, 0)
                        last[key] = value
                        cell = out[a[semconv.RELAY_SLO_ID]][minute_of(int(p["timeUnixNano"]))]
                        cell[1] += delta
                        if a[semconv.RELAY_SLI_GOOD] is True:
                            cell[0] += delta
    return out


def _points(lines: list[str], name: str):
    """(resource, point) for every data point of metric `name`, in export order."""
    for line in lines:
        if not line.strip():
            continue
        for rm in json.loads(line).get("resourceMetrics", []):
            resource = tuple(sorted(_attrs(rm["resource"]["attributes"]).items()))
            for sm in rm["scopeMetrics"]:
                for metric in sm["metrics"]:
                    if metric["name"] == name:
                        body = metric.get("sum") or metric.get("gauge") or {}
                        for p in body.get("dataPoints", []):
                            yield resource, p


def counter_deltas(lines: list[str], name: str) -> list[tuple[datetime, dict, int]]:
    """(minute, attributes, increase) for a cumulative counter, one entry per export point."""
    last: dict[tuple, float] = {}
    out = []
    for resource, p in _points(lines, name):
        attrs = _attrs(p["attributes"])
        key = (resource, p["startTimeUnixNano"], tuple(sorted(attrs.items())))
        value = float(p.get("asInt", p.get("asDouble", 0)))
        out.append((minute_of(int(p["timeUnixNano"])), attrs, value - last.get(key, 0)))
        last[key] = value
    return out


def gauge_latest(lines: list[str], name: str) -> float | None:
    """The newest value of a gauge across all exports (the largest, if several processes report at once)."""
    newest: dict[int, float] = {}
    for _, p in _points(lines, name):
        t = int(p["timeUnixNano"])
        newest[t] = max(newest.get(t, float("-inf")), float(p.get("asInt", p.get("asDouble", 0))))
    return newest[max(newest)] if newest else None


def operational_values(lines: list[str], now: datetime) -> dict:
    """The metric values AL-001 to AL-008 read, from OTLP metric export lines, as of `now`."""
    def total(name: str, minutes: int, where=None, by: str | None = None):
        since = now - timedelta(minutes=minutes)
        sums: dict = defaultdict(float)
        for t, attrs, inc in counter_deltas(lines, name):
            if since < t <= now and (where is None or where(attrs)):
                sums[attrs.get(by, "") if by else ""] += inc
        return dict(sums) if by else sums.get("", 0.0)
    values = {
        "relay.escalation.failed.5m": total("relay.escalation.passes", 5,
                                            lambda a: a.get(semconv.RELAY_ESCALATION_RESULT) == "failed"),
        "relay.escalation.cannot_evaluate.1h": total("relay.escalation.cannot_evaluate", 60),
        "relay.agent.budget_stops.1h": total("relay.agent.runs", 60,
                                             lambda a: a.get(semconv.RELAY_AGENT_STATUS) == "budget",
                                             by=semconv.GEN_AI_AGENT_ID),
        "relay.agent.unknown_outcome.1h": total("relay.agent.unknown_outcome", 60, by=semconv.GEN_AI_AGENT_ID),
    }
    for metric in ("relay.worker.heartbeat_age", "relay.telemetry.overflow"):
        latest = gauge_latest(lines, metric)
        if latest is not None:
            values[metric] = latest
    return values


def series_from_minutes(minutes: dict[datetime, list[int]], start: datetime, end: datetime) -> Series:
    """A dense per-minute Series from `start` to `end` inclusive; minutes with no data count as no events."""
    good, total = [], []
    t = start
    while t <= end:
        g, n = minutes.get(t, (0, 0))
        good.append(g)
        total.append(n)
        t += timedelta(minutes=1)
    return Series(good, total)


class Monitor:
    def __init__(self, slos: dict, alert_rules: dict, router: Router, send, trip=None) -> None:
        self.slos, self.alert_rules, self.router, self.send, self.trip = slos, alert_rules, router, send, trip
        self.sent: set[str] = set()
        self.log: list[tuple[AlertRecord, list[str]]] = []

    def _deliver(self, records: list[AlertRecord]) -> list[AlertRecord]:
        new = []
        for record in sorted(records, key=lambda r: (r.at, r.rule, r.alert_id)):
            if record.alert_id in self.sent:
                continue
            self.sent.add(record.alert_id)
            self.log.append((record, self.router.dispatch(record, self.send, self.trip)))
            new.append(record)
        return new

    def slo_alerts(self, minutes_by_slo: dict, start: datetime, end: datetime) -> list[AlertRecord]:
        out = []
        for slo_id, slo in sorted(self.slos.items()):
            series = series_from_minutes(minutes_by_slo.get(slo_id, {}), start, end)
            for ep in evaluate(series, slo):
                out.append(from_episode(slo_id, ep, lambda i: start + timedelta(minutes=i)))
        return out

    def trail_alerts(self, records: list[dict], ruleset: dict, baseline: detection.Baseline, anchor=None,
                     now: datetime | None = None, since: datetime | None = None) -> list[AlertRecord]:
        """Verify the whole trail first; then evaluate its events from `since` (all if None)."""
        ok, reason = detection.verified_trail(records, anchor)
        if not ok:
            at = now or datetime.now(timezone.utc)
            return [AlertRecord(f"TRAIL-TAMPER:{at.strftime('%Y%m%dT%H%M')}", "TRAIL-TAMPER", at, "page", "security",
                                f"audit trail failed verification: {reason}", ("trail:verify",))]
        events = [e for e in detection.from_trail(records) if since is None or e.at >= since]
        return [from_detection(a) for a in detection.evaluate(events, ruleset, baseline)]

    def event_alerts(self, events: list[detection.Event], ruleset: dict,
                     baseline: detection.Baseline) -> list[AlertRecord]:
        return [from_detection(a) for a in detection.evaluate(events, ruleset, baseline)]

    def tick(self, now: datetime, *, slo_minutes: dict | None = None, slo_start: datetime | None = None,
             values: dict | None = None, alerts: list[AlertRecord] = ()) -> list[AlertRecord]:
        """One evaluation step. Returns the alerts delivered for the first time."""
        records = list(alerts)
        if slo_minutes is not None and slo_start is not None:
            records += self.slo_alerts(slo_minutes, slo_start, now)
        if values:
            records += operational_alerts(self.alert_rules, values, now)
        return self._deliver(records)
