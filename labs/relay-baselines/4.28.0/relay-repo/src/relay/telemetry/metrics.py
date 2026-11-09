"""Metrics: counters, histograms and gauges with a cardinality limit (added in 4.27.0; ADR-036).

Each instrument keeps one series per distinct set of attributes. Attributes pass the same key allowlist
as spans (`relay.telemetry.redact`), so a user ID or an email address cannot become a label. Even allowed
keys can explode: a raw URL path as `http.route` makes one series per task. So each instrument has a
cardinality limit. Past it, new attribute sets are folded into one series marked `otel.metric.overflow`,
as the OpenTelemetry SDK specification describes, and the overflow is counted so a runtime fitness check
can fail on it (`relay.telemetry.fitness`).

Values are cumulative from process start. Export is by `relay.telemetry.otlp`.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field

from . import semconv
from .redact import clean_attributes

DEFAULT_CARDINALITY_LIMIT = 2000  # the SDK specification's default per instrument; Relay's are lower


def _key(attributes: dict) -> tuple:
    return tuple(sorted(attributes.items()))


@dataclass
class Instrument:
    name: str
    kind: str  # counter, histogram, gauge
    unit: str
    description: str
    limit: int
    boundaries: tuple[float, ...] = ()
    series: dict = field(default_factory=dict)
    overflowed: int = 0  # measurements folded into the overflow series
    redactions: Counter = field(default_factory=Counter)

    def _series_key(self, attributes: dict | None) -> tuple:
        clean, _ = clean_attributes(dict(attributes or {}), self.redactions)
        key = _key(clean)
        if key not in self.series and len(self.series) >= self.limit:
            self.overflowed += 1
            key = _key({semconv.OVERFLOW: True})
        return key

    def add(self, value: float = 1, attributes: dict | None = None) -> None:
        if self.kind != "counter" or value < 0:
            raise ValueError(f"{self.name}: counters only go up")
        key = self._series_key(attributes)
        self.series[key] = self.series.get(key, 0) + value

    def record(self, value: float, attributes: dict | None = None) -> None:
        if self.kind != "histogram":
            raise ValueError(f"{self.name} is not a histogram")
        key = self._series_key(attributes)
        point = self.series.setdefault(key, {"count": 0, "sum": 0.0, "min": value, "max": value,
                                             "buckets": [0] * (len(self.boundaries) + 1)})
        point["count"] += 1
        point["sum"] += value
        point["min"], point["max"] = min(point["min"], value), max(point["max"], value)
        point["buckets"][bisect_left(self.boundaries, value)] += 1  # bucket i holds (b[i-1], b[i]]

    def set(self, value: float, attributes: dict | None = None) -> None:
        if self.kind != "gauge":
            raise ValueError(f"{self.name} is not a gauge")
        self.series[self._series_key(attributes)] = value

    def points(self) -> list[tuple[dict, object]]:
        return [(dict(k), v) for k, v in sorted(self.series.items(), key=lambda kv: repr(kv[0]))]


class Meter:
    def __init__(self, default_limit: int = 200) -> None:
        self.instruments: dict[str, Instrument] = {}
        self.default_limit = default_limit

    def _get(self, name: str, kind: str, unit: str, description: str, limit: int | None,
             boundaries: tuple[float, ...] = ()) -> Instrument:
        inst = self.instruments.get(name)
        if inst is None:
            inst = self.instruments[name] = Instrument(name, kind, unit, description,
                                                       limit or self.default_limit, tuple(boundaries))
        elif inst.kind != kind:
            raise ValueError(f"{name} is already a {inst.kind}")
        return inst

    def counter(self, name: str, unit: str = "1", description: str = "", limit: int | None = None) -> Instrument:
        return self._get(name, "counter", unit, description, limit)

    def histogram(self, name: str, unit: str = "s", description: str = "", limit: int | None = None,
                  boundaries: tuple[float, ...] = semconv.DURATION_BUCKETS) -> Instrument:
        return self._get(name, "histogram", unit, description, limit, boundaries)

    def gauge(self, name: str, unit: str = "1", description: str = "", limit: int | None = None) -> Instrument:
        return self._get(name, "gauge", unit, description, limit)

    def overflow_report(self) -> dict[str, int]:
        return {name: inst.overflowed for name, inst in sorted(self.instruments.items()) if inst.overflowed}

    def series_counts(self) -> dict[str, int]:
        return {name: len(inst.series) for name, inst in sorted(self.instruments.items())}
