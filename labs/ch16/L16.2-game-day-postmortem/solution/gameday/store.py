"""A small telemetry store for one scenario, seen as of a moment (provided).

Metrics are per-minute series named `metric:<name>` or `share:<name>`; events and alerts are named
`event:<id>` and `alert:<rule>`. `as_of` hides everything after a moment, so a hypothesis is judged on what
the responders could have seen when it was made.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc


def parse(text: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise ValueError(text)


def read_csv(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    keys = lines[0].split(",")
    out = []
    for ln in lines[1:]:
        row = {}
        for k, v in zip(keys, ln.split(",")):
            row[k] = v if k in ("minute", "network") else float(v)
        out.append(row)
    return out


class Store:
    def __init__(self, day: datetime, rows: list[dict], events: list[dict], alerts: list, as_of: datetime | None = None,
                 baseline: tuple[str, str] = ("00:00", "00:30"), mechanisms: dict | None = None):
        self.day, self.rows, self.events, self.alerts = day, rows, events, alerts
        self.as_of = as_of
        self.baseline = baseline                  # the checker's quiet window, never the model's
        self.mechanisms = dict(mechanisms or {})  # cause -> the share series its mechanism would show
        self.series: dict[str, dict[datetime, float]] = {}
        for row in rows:
            t = parse(row["minute"])
            for k, v in row.items():
                if k != "minute":
                    self.series.setdefault(f"metric:{k}", {})[t] = v
        self._derive()

    def _derive(self) -> None:
        req, slow = self.series.get("metric:api_requests", {}), self.series.get("metric:api_slow", {})
        self.series["metric:api_slow_share"] = {t: slow[t] / req[t] if req[t] else 0.0 for t in req}
        if "metric:db_ms_signin" in self.series:
            parts = ("signin", "notify", "other")
            for p in parts:
                self.series[f"share:db_{p}"] = {
                    t: self.series[f"metric:db_ms_{p}"][t] / math.fsum(self.series[f"metric:db_ms_{q}"][t] for q in parts)
                    for t in self.series["metric:db_ms_signin"]}
        if "metric:share_db_of_request" in self.series:
            self.series["share:db_of_request"] = self.series["metric:share_db_of_request"]

    def mechanism(self, cause: str) -> str | None:
        return self.mechanisms.get(cause)

    def at(self, hhmm: str) -> datetime:
        h, m = hhmm.split(":")
        return self.day.replace(hour=int(h), minute=int(m))

    def seen(self, t: datetime) -> bool:
        return self.as_of is None or t <= self.as_of

    def values(self, name: str, a: str, b: str) -> list[float]:
        s = self.series.get(name, {})
        lo, hi = self.at(a), self.at(b)
        return [v for t, v in sorted(s.items()) if lo <= t <= hi and self.seen(t)]

    def mean(self, name: str, a: str, b: str) -> float | None:
        vals = self.values(name, a, b)
        return math.fsum(vals) / len(vals) if vals else None  # fsum: same result on every Python version

    def onset(self, name: str, baseline: list[str], factor: float) -> datetime | None:
        """The first minute after the baseline window where the series reaches factor x its baseline mean."""
        base = self.mean(name, *baseline)
        if base is None:
            return None
        start = self.at(baseline[1])
        for t, v in sorted(self.series.get(name, {}).items()):
            if t > start and self.seen(t) and v >= factor * max(base, 1e-9):
                return t
        return None

    def event(self, ref: str) -> dict | None:
        eid = ref.split(":", 1)[1]
        for e in self.events:
            if e["id"] == eid and self.seen(parse(e["at"])):
                return e
        return None

    def alert(self, ref: str):
        rule = ref.split(":", 1)[1]
        seen = [a for a in self.alerts if a.rule == rule and self.seen(a.at)]
        return min(seen, key=lambda a: a.at) if seen else None

    def time_of(self, ref: str) -> datetime | None:
        """When a cause or effect began: an event's time, an alert's time, or a metric's recorded start."""
        if ref.startswith("event:"):
            e = self.event(ref)
            return parse(e["at"]) if e else None
        if ref.startswith("alert:"):
            a = self.alert(ref)
            return a.at if a else None
        return None

    def removal_of(self, ref: str) -> datetime | None:
        """When a change was undone (a rollback that `removes` it, once done), if it was and that is visible."""
        eid = ref.split(":", 1)[1]
        for e in self.events:
            if e.get("removes") == eid and "done" in e and self.seen(parse(e["done"])):
                return parse(e["done"])
        return None

    def view(self, as_of: datetime | None) -> "Store":
        other = Store.__new__(Store)
        other.__dict__.update(self.__dict__)
        other.as_of = as_of
        return other


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def minute_after(t: datetime, minutes: int) -> datetime:
    return t + timedelta(minutes=minutes)
