"""Drive Relay 4.27.0's service with telemetry on, and compare it with a naive access log (provided).

The naive log is what an HTTP server's default access log plus "log the request for debugging" would keep:
method, full path with the query string, every header and the body. Both outputs go through the same leak
scan, `relay.telemetry.redact.leaks`, which counts what the redactor would still replace.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from pathlib import Path

from relay.service.__main__ import build_app
from relay.service.directory import demo_directory
from relay.service.telemetry import TelemetryMiddleware
from relay.telemetry import IdSource, Logger, Meter, Tracer
from relay.telemetry.fitness import cardinality_check, telemetry_leak_check
from relay.telemetry.otlp import FileExporter, MemoryExporter
from relay.telemetry.redact import leaks
from relay.telemetry.runs import run_signals, trace_run

from .data import DATA, jsonl


class Clock:
    def __init__(self, start_ns: int = 1_801_670_400_000_000_000):  # 2027-02-02T15:00:00Z
        self.t = start_ns

    def __call__(self) -> int:
        self.t += 7_000_000  # 7 ms per reading
        return self.t


def environ_for(req: dict) -> dict:
    body = json.dumps(req["body"]).encode() if "body" in req else b""
    env = {"REQUEST_METHOD": req["method"], "PATH_INFO": req["path"], "QUERY_STRING": req.get("query", ""),
           "wsgi.input": io.BytesIO(body), "CONTENT_LENGTH": str(len(body)),
           "REMOTE_ADDR": req.get("remote_addr", "203.0.113.45")}
    if "token" in req:
        env["HTTP_AUTHORIZATION"] = f"Bearer {req['token']}"
    if "idempotency_key" in req:
        env["HTTP_IDEMPOTENCY_KEY"] = req["idempotency_key"]
    for k, v in req.get("headers", {}).items():
        env["HTTP_" + k.upper().replace("-", "_")] = v
    return env


def naive_line(env: dict, status: str, body: bytes) -> str:
    headers = {k[5:].lower().replace("_", "-"): v for k, v in env.items() if k.startswith("HTTP_")}
    path = env["PATH_INFO"] + ("?" + env["QUERY_STRING"] if env["QUERY_STRING"] else "")
    return json.dumps({"client": env["REMOTE_ADDR"], "request": f"{env['REQUEST_METHOD']} {path}", "status": status,
                       "headers": headers, "body": body.decode("utf-8", "replace")}, sort_keys=True)


def exercise(out_dir: Path) -> dict:
    """Send the request script through the instrumented service; return what was exported and found."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("traces.jsonl", "metrics.jsonl", "logs.jsonl", "naive-access.log"):
        (out_dir / name).unlink(missing_ok=True)
    exporter = FileExporter(out_dir, "relay-service", "lab")
    clock, meter = Clock(), Meter()
    app = TelemetryMiddleware(build_app(":memory:", demo_directory(), demo=True), Tracer(exporter, IdSource(seed=16),
                              clock_ns=clock), meter, Logger(exporter, clock_ns=clock), b"lab-16.1-key" * 3,
                              clock_ns=clock)
    statuses: Counter = Counter()
    naive = []
    for req in jsonl(DATA / "requests" / "script.jsonl"):
        env = environ_for(req)
        body = env["wsgi.input"].getvalue()
        seen = {}
        b"".join(app(env, lambda status, headers: seen.update(status=status)))
        statuses[seen["status"].split(" ")[0]] += 1
        naive.append(naive_line(env, seen["status"], body))
    spans, logs = len(exporter.spans), len(exporter.logs)
    exporter.flush(meter, 0, clock())
    (out_dir / "naive-access.log").write_text("\n".join(naive) + "\n", encoding="utf-8")
    naive_found: Counter = Counter()
    for line in naive:
        naive_found.update(leaks(line))
    rf3 = telemetry_leak_check([out_dir / n for n in ("traces.jsonl", "metrics.jsonl", "logs.jsonl")])
    routes = sorted({kv["value"]["stringValue"] for line in (out_dir / "traces.jsonl").read_text().splitlines()
                     for rs in json.loads(line)["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]
                     for kv in s["attributes"] if kv["key"] == "http.route"})
    return {"requests": sum(statuses.values()), "statuses": dict(sorted(statuses.items())), "spans": spans,
            "security_events": logs, "routes": routes, "rf003": rf3, "rf004": cardinality_check(meter),
            "naive_findings": dict(sorted(naive_found.items())), "naive_total": sum(naive_found.values()),
            "redactions_at_export": dict(sorted(app.tracer.redactions.items()))}


def agent_traces() -> dict:
    """Trace every run in the journal and count the alert inputs (provided)."""
    from .data import journal
    j = journal()
    exp, meter = MemoryExporter(), Meter()
    tracer = Tracer(exp, IdSource(seed=10))
    for run in j["runs"]:
        trace_run(tracer, meter, run, j["steps"][run["run_id"]])
    signals = run_signals(j["runs"], j["steps"])
    by_status = {p["relay.agent.status"]: v for p, v in meter.instruments["relay.agent.runs"].points()}
    return {"runs": len(j["runs"]), "spans": len(exp.spans), "by_status": dict(sorted(by_status.items())),
            "signals": signals, "dropped": dict(tracer.redactions)}
