"""The service's telemetry middleware, its wiring in wsgi, the pager client and the monitor CLI (4.27.0, ADR-036,
ADR-038). Requests are built by hand; nothing listens on a socket."""

import io
import json

import pytest

from relay.service.__main__ import build_app
from relay.service.app import RelayApp
from relay.service.directory import demo_directory
from relay.service.monitor import main as monitor_main
from relay.service.pager import PagerClient
from relay.service.telemetry import TelemetryMiddleware, client_network, route_template
from relay.service.wsgi import ConfigError, instrument
from relay.store import TaskStore
from relay.telemetry import IdSource, Logger, MemoryExporter, Meter, Tracer
from relay.telemetry.alerting import AlertRecord
from relay.worker import TriageQueue

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class Clock:
    def __init__(self):
        self.t = 1_800_000_000_000_000_000

    def __call__(self):
        self.t += 40_000_000  # every reading is 40 ms after the last
        return self.t


def stack():
    exporter, meter = MemoryExporter(), Meter()
    app = build_app(":memory:", demo_directory(), demo=True)
    mw = TelemetryMiddleware(app, Tracer(exporter, IdSource(seed=1)), meter, Logger(exporter), b"k" * 32,
                             clock_ns=Clock())
    return mw, exporter, meter


def call(app, path, token=None, method="GET", body=None, **headers):
    data = json.dumps(body).encode() if body is not None else b""
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": "email=jane.doe@example.com",
               "wsgi.input": io.BytesIO(data), "CONTENT_LENGTH": str(len(data)), "REMOTE_ADDR": "203.0.113.45"}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    environ.update({f"HTTP_{k.upper()}": v for k, v in headers.items()})
    seen = {}
    b"".join(app(environ, lambda status, hdrs: seen.update(status=status)))
    return seen["status"]


@pytest.mark.parametrize("path,template", [
    ("/healthz", "/healthz"), ("/v1/projects/10/tasks/100", "/v1/projects/{pid}/tasks/{tid}"),
    ("/v1/triage-jobs", "/v1/triage-jobs"), ("/v1/triage-jobs/7", "/v1/triage-jobs/{id}"),
    ("/v1/projects/10/escalation-rules/R-1", "/v1/projects/{pid}/escalation-rules/{rid}"),
    ("/v1/projects/10/tasks/100/acknowledge", "/v1/projects/{pid}/tasks/{tid}/acknowledge"),
    ("/v1/projects/10/tasks/100/ack", None), ("/wp-admin/setup.php", None)])
def test_routes_are_templates_and_unknown_paths_have_none(path, template):
    assert route_template(path) == template


def test_a_request_becomes_one_server_span_with_method_route_and_status_only():
    mw, exp, meter = stack()
    assert call(mw, "/v1/projects/10/tasks/100", "demo-owner", traceparent=TRACEPARENT).startswith("200")
    span, = exp.spans
    assert span.name == "GET /v1/projects/{pid}/tasks/{tid}" and span.kind == "SERVER"
    assert span.attributes == {"http.request.method": "GET", "http.route": "/v1/projects/{pid}/tasks/{tid}",
                               "http.response.status_code": 200}
    # The caller's context is a link, not a parent: Relay starts its own trace.
    assert span.parent_span_id is None and span.trace_id != TRACEPARENT[3:35]
    assert span.links[0]["trace_id"] == TRACEPARENT[3:35]
    assert exp.logs == []  # nothing security-relevant happened
    sli = meter.instruments["relay.sli.events"].points()
    assert ({"relay.slo.id": "SLO-API-AVAIL", "relay.sli.good": True}, 1) in sli
    assert ({"relay.slo.id": "SLO-API-LATENCY", "relay.sli.good": True}, 1) in sli  # 40 ms


def test_four_hundreds_are_not_span_errors_but_401s_are_security_events():
    mw, exp, _ = stack()
    assert call(mw, "/v1/triage-jobs/1", "stolen-token").startswith("401")
    span, = exp.spans
    assert span.status == "UNSET"
    log, = exp.logs
    assert log.body == "auth.failure" and log.trace_id == span.trace_id
    assert log.attributes["relay.client.network"] == "203.0.113.0/24"
    assert len(log.attributes["relay.credential.fingerprint"]) == 16
    text = json.dumps([span.attributes, log.attributes])
    assert "stolen-token" not in text and "203.0.113.45" not in text and "jane.doe" not in text


def test_an_unhandled_error_is_a_5xx_span_error_and_a_bad_sli_event():
    mw, exp, meter = stack()
    mw.app.tasks = None  # the next task read raises inside the app, which answers 500
    assert call(mw, "/v1/projects/10/tasks/100", "demo-owner").startswith("500")
    assert exp.spans[0].status == "ERROR" and exp.spans[0].attributes["error.type"] == "500"
    assert ({"relay.slo.id": "SLO-API-AVAIL", "relay.sli.good": False}, 1) in \
        meter.instruments["relay.sli.events"].points()


def test_unknown_methods_and_paths_do_not_create_series():
    mw, exp, meter = stack()
    for i in range(20):
        call(mw, f"/probe/{i}", method="BREW")
    assert {s.name for s in exp.spans} == {"_OTHER"}
    assert len(meter.instruments["http.server.request.duration"].series) == 1


@pytest.mark.parametrize("peer,xff,trusted,expected", [
    ("10.0.1.5", "198.51.100.7", ("10.0.0.0/16",), "198.51.100.0/24"),
    ("10.0.1.5", "6.6.6.6, 198.51.100.7", ("10.0.0.0/16",), "198.51.100.0/24"),  # the proxy's hop, not the claim
    ("203.0.113.45", "198.51.100.7", ("10.0.0.0/16",), "203.0.113.0/24"),     # untrusted peer: XFF ignored
    ("2001:db8:1234:5678::1", "", (), "2001:db8:1234::/48"), ("not-an-ip", "", (), "unknown")])
def test_client_network_trusts_forwarded_for_only_from_the_proxy(peer, xff, trusted, expected):
    import ipaddress
    nets = tuple(ipaddress.ip_network(n) for n in trusted)
    assert client_network({"REMOTE_ADDR": peer, "HTTP_X_FORWARDED_FOR": xff}, nets) == expected


def test_wsgi_instruments_only_when_configured(tmp_path):
    app = RelayApp(demo_directory(), TaskStore(), TriageQueue())
    assert instrument(app, {}) is app
    wrapped = instrument(app, {"RELAY_TELEMETRY_DIR": str(tmp_path), "RELAY_TELEMETRY_KEY": "00" * 32,
                               "RELAY_TRUSTED_PROXIES": "10.0.0.0/16"}, flush_every_s=0.0)
    assert isinstance(wrapped, TelemetryMiddleware) and wrapped.queue is app.queue
    call(wrapped, "/healthz")
    assert (tmp_path / "traces.jsonl").is_file() and (tmp_path / "metrics.jsonl").is_file()
    with pytest.raises(ConfigError):
        instrument(app, {"RELAY_TELEMETRY_DIR": str(tmp_path), "RELAY_TELEMETRY_KEY": "not hex"})


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_pager_client_sends_ids_and_evidence_never_values_and_retries():
    calls = []

    def opener(req, timeout):
        calls.append(json.loads(req.data))
        if len(calls) == 1:
            raise OSError("connection reset")
        return FakeResponse(202)

    client = PagerClient("https://events.pager.example/v2/enqueue", {"security-oncall": "rk-1"}, opener=opener)
    from datetime import datetime, timezone
    at = datetime(2027, 2, 18, 14, 5, tzinfo=timezone.utc)
    alert = AlertRecord("DR-001:20270218T1405:x", "DR-001", at, "page", "security", "DR-001 for x: 4 over 3",
                        ("trail:6",), "x")
    assert client.page(alert, "security-oncall", at) is True and len(calls) == 2
    body = calls[-1]
    assert body["dedup_key"] == alert.alert_id and body["routing_key"] == "rk-1"
    assert body["payload"]["custom_details"] == {"rule": "DR-001", "category": "security", "evidence": ["trail:6"]}
    with pytest.raises(ValueError):
        PagerClient("http://events.pager.example", {})


def test_monitor_cli_dry_run_reads_otlp_logs_and_prints_alerts(tmp_path, capsys):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    lines = []
    for i in range(205):
        attrs = [{"key": "relay.security.event", "value": {"stringValue": "auth.failure"}},
                 {"key": "relay.client.network", "value": {"stringValue": "198.51.100.0/24"}},
                 {"key": "relay.credential.fingerprint", "value": {"stringValue": f"fp{i:04d}"}}]
        t = 1_802_959_260_000_000_000 + i * 1_000_000_000  # 2027-02-18T14:01:00Z plus i seconds
        lines.append(json.dumps({"resourceLogs": [{"resource": {"attributes": []}, "scopeLogs": [{"scope": {},
                     "logRecords": [{"timeUnixNano": str(t), "attributes": attrs}]}]}]}))
    (tmp_path / "logs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monitor_main(["--repo", str(root), "--logs", str(tmp_path / "logs.jsonl"), "--since", "2027-02-18T14:00:00Z",
                  "--now", "2027-02-18T14:30:00Z", "--dry-run"])
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["rule"] for r in rows] == ["SD-001", "SD-002"]
    assert rows[0]["done"] == ["page:security-oncall"] and rows[0]["at"] == "2027-02-18T14:05:00Z"
