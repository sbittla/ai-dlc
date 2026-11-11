"""OTLP's JSON encoding, and exporters to memory and to files (added in 4.27.0; ADR-036).

Relay does not send telemetry over the network itself. A process writes OTLP JSON lines (one export request
per line, one file per signal) to a task-local directory, and the OpenTelemetry Collector running beside
it in the same task reads the files, applies its own redaction and sampling processors, and exports to the
backend (ADR-036, `infra/monitoring/collector.yaml`). That keeps Relay's no-network rule for every package
but the service's HTTP boundary (AR4), and gives one place, the collector, that egresses.

The JSON follows OTLP's protobuf-to-JSON mapping as the OTLP specification describes it: trace and span
IDs as lowercase hex, 64-bit integers and nanosecond times as decimal strings, enums as integers.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import __version__
from . import semconv

SPAN_KIND = {"INTERNAL": 1, "SERVER": 2, "CLIENT": 3, "PRODUCER": 4, "CONSUMER": 5}
STATUS_CODE = {"UNSET": 0, "OK": 1, "ERROR": 2}
CUMULATIVE = 2  # AggregationTemporality


def any_value(value) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [any_value(v) for v in value]}}
    return {"stringValue": str(value)}


def key_values(attributes: dict) -> list[dict]:
    return [{"key": k, "value": any_value(v)} for k, v in sorted(attributes.items())]


def resource(service: str, environment: str) -> dict:
    return {"attributes": key_values({semconv.SERVICE_NAME: service, semconv.SERVICE_VERSION: __version__,
                                      semconv.DEPLOYMENT_ENVIRONMENT: environment})}


SCOPE = {"name": "relay.telemetry", "version": __version__}


def span_json(span) -> dict:
    out = {"traceId": span.trace_id, "spanId": span.span_id, "name": span.name, "kind": SPAN_KIND[span.kind],
           "startTimeUnixNano": str(span.start_ns), "endTimeUnixNano": str(span.end_ns),
           "attributes": key_values(span.attributes),
           "status": {"code": STATUS_CODE[span.status], **({"message": span.status_message}
                                                           if span.status_message else {})}}
    if span.parent_span_id:
        out["parentSpanId"] = span.parent_span_id
    if span.events:
        out["events"] = [{"name": e["name"], "timeUnixNano": str(e["time_ns"]),
                          "attributes": key_values(e["attributes"])} for e in span.events]
    if span.links:
        out["links"] = [{"traceId": link["trace_id"], "spanId": link["span_id"]} for link in span.links]
    return out


def traces_request(spans, res: dict) -> dict:
    return {"resourceSpans": [{"resource": res, "scopeSpans": [{"scope": SCOPE,
                                                                "spans": [span_json(s) for s in spans]}]}]}


def log_json(record) -> dict:
    out = {"timeUnixNano": str(record.time_ns), "severityNumber": record.severity_number,
           "severityText": record.severity_text, "body": {"stringValue": record.body},
           "attributes": key_values(record.attributes)}
    if record.trace_id:
        out["traceId"], out["spanId"] = record.trace_id, record.span_id
    return out


def logs_request(records, res: dict) -> dict:
    return {"resourceLogs": [{"resource": res, "scopeLogs": [{"scope": SCOPE,
                                                              "logRecords": [log_json(r) for r in records]}]}]}


def metrics_request(meter, res: dict, start_ns: int, now_ns: int) -> dict:
    metrics = []
    for name, inst in sorted(meter.instruments.items()):
        points = []
        for attrs, value in inst.points():
            base = {"attributes": key_values(attrs), "startTimeUnixNano": str(start_ns), "timeUnixNano": str(now_ns)}
            if inst.kind == "histogram":
                points.append({**base, "count": str(value["count"]), "sum": value["sum"], "min": value["min"],
                               "max": value["max"], "bucketCounts": [str(c) for c in value["buckets"]],
                               "explicitBounds": list(inst.boundaries)})
            elif isinstance(value, int):
                points.append({**base, "asInt": str(value)})
            else:
                points.append({**base, "asDouble": float(value)})
        body = {"name": name, "unit": inst.unit, "description": inst.description}
        if inst.kind == "counter":
            body["sum"] = {"dataPoints": points, "aggregationTemporality": CUMULATIVE, "isMonotonic": True}
        elif inst.kind == "histogram":
            body["histogram"] = {"dataPoints": points, "aggregationTemporality": CUMULATIVE}
        else:
            body["gauge"] = {"dataPoints": points}
        metrics.append(body)
    overflowed = sum(meter.overflow_report().values())
    if overflowed:  # RF-004 and AL-008 read this from the export
        metrics.append({"name": "relay.telemetry.overflow", "unit": "{measurement}",
                        "description": "measurements folded into overflow series",
                        "gauge": {"dataPoints": [{"attributes": [], "timeUnixNano": str(now_ns),
                                                  "asInt": str(overflowed)}]}})
    return {"resourceMetrics": [{"resource": res, "scopeMetrics": [{"scope": SCOPE, "metrics": metrics}]}]}


class MemoryExporter:
    """Keeps finished spans and log records in lists (tests, labs and the game-day simulation)."""

    def __init__(self) -> None:
        self.spans, self.logs = [], []

    def export_span(self, span) -> None:
        self.spans.append(span)

    def export_log(self, record) -> None:
        self.logs.append(record)


class FileExporter(MemoryExporter):
    """Buffers like MemoryExporter; `flush` appends one OTLP JSON line per signal to files in `directory`."""

    def __init__(self, directory: str | Path, service: str, environment: str) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.res = resource(service, environment)

    def _append(self, name: str, payload: dict) -> None:
        with open(self.directory / name, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")

    def flush(self, meter=None, start_ns: int = 0, now_ns: int = 0) -> None:
        if self.spans:
            self._append("traces.jsonl", traces_request(self.spans, self.res))
            self.spans = []
        if self.logs:
            self._append("logs.jsonl", logs_request(self.logs, self.res))
            self.logs = []
        if meter is not None and meter.instruments:
            self._append("metrics.jsonl", metrics_request(meter, self.res, start_ns, now_ns))
