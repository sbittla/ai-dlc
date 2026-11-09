"""Traces, metrics, logs and their OTLP JSON form (4.27.0, ADR-036). Expected values are worked by hand."""

import json

import pytest

from relay.telemetry import FileExporter, IdSource, Logger, MemoryExporter, Meter, Tracer, parse_traceparent
from relay.telemetry import format_traceparent, semconv
from relay.telemetry.otlp import metrics_request, traces_request, resource
from relay.telemetry.trace import ERROR, SERVER


def tracer():
    exporter = MemoryExporter()
    return Tracer(exporter, IdSource(seed=7), clock_ns=lambda: 1_000), exporter


def test_ids_are_hex_of_the_right_length_and_never_zero():
    ids = IdSource(seed=1)
    trace_id, span_id = ids.trace_id(), ids.span_id()
    assert len(trace_id) == 32 and len(span_id) == 16
    assert int(trace_id, 16) and int(span_id, 16)


@pytest.mark.parametrize("header,ok", [
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", True),
    ("00-00000000000000000000000000000000-00f067aa0ba902b7-01", False),  # all-zero trace ID
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01", False),  # all-zero span ID
    ("ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", False),  # version ff is invalid
    ("00-4BF92F3577B34DA6A3CE929D0E0E4736-00f067aa0ba902b7-01", False),  # upper case is not allowed
    ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7", False),
    ("", False), (None, False),
])
def test_traceparent_is_parsed_strictly(header, ok):
    assert (parse_traceparent(header) is not None) is ok


def test_child_spans_share_the_trace_and_point_at_their_parent():
    t, exp = tracer()
    root = t.start("root", SERVER)
    child = t.start("child", parent=root)
    t.end(child)
    t.end(root)
    assert child.trace_id == root.trace_id and child.parent_span_id == root.span_id
    assert [s.name for s in exp.spans] == ["child", "root"]
    assert format_traceparent(root) == f"00-{root.trace_id}-{root.span_id}-01"


def test_ending_a_span_cleans_its_attributes_events_and_message():
    t, exp = tracer()
    span = t.start("op", attributes={"http.route": "/v1/x", "enduser.id": "priya.n",
                                     "gen_ai.output.messages": "the answer"})
    span.add_event("retry", 2_000, {"error.type": "timeout", "url.full": "https://x/?token=abc12345"})
    t.end(span, ERROR, "failed for jane.doe@example.com")
    assert span.attributes == {"http.route": "/v1/x"}
    assert span.events[0]["attributes"] == {"error.type": "timeout"}
    assert span.status_message == "failed for [redacted:email]"
    assert t.redactions == {"unknown-key": 2, "content-key": 1, "email": 1}


def test_counter_histogram_and_gauge():
    m = Meter()
    c = m.counter("c")
    c.add(2, {"http.route": "/a"})
    c.add(3, {"http.route": "/a"})
    with pytest.raises(ValueError):
        c.add(-1)
    h = m.histogram("h", boundaries=(0.1, 0.25, 1.0))
    for v in (0.05, 0.1, 0.25, 0.3, 5.0):  # bucket i holds (b[i-1], b[i]]
        h.record(v)
    (attrs, point), = h.points()
    assert c.points() == [({"http.route": "/a"}, 5)]
    assert point["buckets"] == [2, 1, 1, 1] and point["count"] == 5 and point["max"] == 5.0
    g = m.gauge("g")
    g.set(10.0)
    g.set(12.5)
    assert g.points() == [({}, 12.5)]


def test_cardinality_limit_folds_new_attribute_sets_into_the_overflow_series():
    m = Meter()
    c = m.counter("requests", limit=3)
    for task in range(10):  # a raw path as a label: one series per task, until the limit
        c.add(1, {"http.route": f"/v1/projects/1/tasks/{task}"})
    assert len(c.series) == 4 and c.overflowed == 7
    assert ({semconv.OVERFLOW: True}, 7) in c.points()
    assert m.overflow_report() == {"requests": 7}


def test_metric_attributes_pass_the_allowlist():
    m = Meter()
    m.counter("c").add(1, {"user.email": "jane.doe@example.com", "http.route": "/a"})
    assert m.instruments["c"].points() == [({"http.route": "/a"}, 1)]


def test_log_records_carry_trace_context_and_are_redacted():
    t, exp = tracer()
    span = t.start("op")
    rec = Logger(exp, clock_ns=lambda: 5).emit("WARN", "retrying for jane.doe@example.com",
                                                {"relay.security.event": "auth.failure", "client.address": "1.2.3.4"},
                                                span=span)
    assert rec.body == "retrying for [redacted:email]" and rec.attributes == {"relay.security.event": "auth.failure"}
    assert (rec.trace_id, rec.span_id, rec.severity_number) == (span.trace_id, span.span_id, 13)


def test_otlp_json_uses_hex_ids_string_nanos_and_integer_enums():
    t, _ = tracer()
    span = t.start("GET /healthz", SERVER, attributes={"http.response.status_code": 200}, start_ns=10)
    t.end(span, end_ns=25)
    body = traces_request([span], resource("relay-service", "nonprod"))
    s = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert s["traceId"] == span.trace_id and s["kind"] == 2 and s["status"] == {"code": 0}
    assert (s["startTimeUnixNano"], s["endTimeUnixNano"]) == ("10", "25")
    assert s["attributes"] == [{"key": "http.response.status_code", "value": {"intValue": "200"}}]
    res = {kv["key"]: kv["value"]["stringValue"] for kv in body["resourceSpans"][0]["resource"]["attributes"]}
    assert res == {"service.name": "relay-service", "service.version": "4.27.0",
                   "deployment.environment.name": "nonprod"}


def test_file_exporter_writes_one_request_per_signal_per_flush(tmp_path):
    exp = FileExporter(tmp_path, "relay-worker", "nonprod")
    t = Tracer(exp, IdSource(seed=3), clock_ns=lambda: 1)
    m = Meter()
    m.counter("relay.worker.passes").add(1, {"relay.worker.outcome": "idle"})
    t.end(t.start("worker.pass"))
    Logger(exp, clock_ns=lambda: 1).emit("INFO", "pass")
    exp.flush(m, 0, 60_000_000_000)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["logs.jsonl", "metrics.jsonl", "traces.jsonl"]
    metric = json.loads((tmp_path / "metrics.jsonl").read_text())["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
    assert metric["sum"]["isMonotonic"] is True and metric["sum"]["dataPoints"][0]["asInt"] == "1"
    exp.flush(m, 0, 120_000_000_000)  # nothing new to trace or log: only metrics again
    assert len((tmp_path / "traces.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "metrics.jsonl").read_text().splitlines()) == 2
    assert metrics_request(Meter(), resource("x", "y"), 0, 0)["resourceMetrics"][0]["scopeMetrics"][0]["metrics"] == []
