"""The monitor command evaluates what ADR-038 says it evaluates (4.27.0): AL rules from metrics, the leak scan and
the database; RELAY_AUTOMATION; no phantom kill-switch trips; grouping through the pager's deduplication key."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from relay.audit import AuditTrail
from relay.service.monitor import main as monitor_main
from relay.service.pager import PagerClient
from relay.telemetry import Meter
from relay.telemetry.alerting import AlertRecord, Pager, Router, load_json
from relay.telemetry.monitor import operational_values
from relay.telemetry.otlp import metrics_request, resource
from relay.worker import TriageQueue

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2027, 2, 18, 14, 0, tzinfo=timezone.utc)
NS = lambda t: int(t.timestamp() * 1e9)  # noqa: E731


def export(meter, at):
    return json.dumps(metrics_request(meter, resource("relay-worker", "nonprod"), NS(T0), NS(at)))


def run(tmp_path, capsys, monkeypatch, automation=None, **files):
    if automation is None:
        monkeypatch.delenv("RELAY_AUTOMATION", raising=False)
    else:
        monkeypatch.setenv("RELAY_AUTOMATION", automation)
    argv = ["--repo", str(ROOT), "--since", "2027-02-18T14:00:00Z", "--now", "2027-02-18T14:30:00Z", "--dry-run"]
    for name, text in files.items():
        if name == "db":
            argv += ["--db", text]
            continue
        path = tmp_path / f"{name}.jsonl"
        path.write_text(text, encoding="utf-8")
        argv += [f"--{name}", str(path)]
    monitor_main(argv)
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_operational_values_come_from_counter_increases_and_gauges():
    m = Meter()
    passes = m.counter("relay.escalation.passes")
    lines = []
    passes.add(1, {"relay.escalation.result": "ok"})
    lines.append(export(m, T0 + timedelta(minutes=20)))
    passes.add(2, {"relay.escalation.result": "failed"})
    m.gauge("relay.worker.heartbeat_age").set(320.0)
    lines.append(export(m, T0 + timedelta(minutes=28)))
    values = operational_values(lines, T0 + timedelta(minutes=30))
    assert values["relay.escalation.failed.5m"] == 2 and values["relay.worker.heartbeat_age"] == 320.0


def test_the_monitor_raises_al_rules_from_metrics_and_the_database(tmp_path, capsys, monkeypatch):
    m = Meter()
    m.counter("relay.escalation.passes").add(3, {"relay.escalation.result": "failed"})
    c = m.counter("relay.overflowing", limit=1)
    c.add(1, {"http.route": "/a"})
    c.add(1, {"http.route": "/b"})  # folded into the overflow series: AL-008
    db = str(tmp_path / "relay.db")
    TriageQueue(db).heartbeat("worker-1", (T0 + timedelta(minutes=20)).timestamp())  # 600 s before --now
    rows = run(tmp_path, capsys, monkeypatch, metrics=export(m, T0 + timedelta(minutes=29)) + "\n", db=db)
    assert {r["rule"]: r["done"] for r in rows} == {"AL-001": ["page:platform-oncall"],
                                                     "AL-003": ["ticket:platform-tickets"],
                                                     "AL-008": ["ticket:platform-tickets"]}


def test_the_leak_scan_pages_security_on_personal_data_in_the_inputs(tmp_path, capsys, monkeypatch):
    dirty = {"resourceLogs": [{"resource": {"attributes": []}, "scopeLogs": [{"scope": {}, "logRecords": [
        {"timeUnixNano": str(NS(T0)), "body": {"stringValue": "retry for jane.doe@example.com"}, "attributes": []}]}]}]}
    rows = run(tmp_path, capsys, monkeypatch, logs=json.dumps(dirty) + "\n")
    assert [(r["rule"], r["done"]) for r in rows] == [("AL-007", ["page:security-oncall"])]


def trail_lines():
    t = AuditTrail(clock=lambda: "2027-02-17T10:00:00Z")
    t.append(agent_id="analytics-sync", owner="lena.k", action="export.start", resource="p", outcome="ok",
             source="relay-ops-host", at="2027-02-17T10:00:00Z")
    for m in (1, 2, 3, 4):
        t.append(agent_id="analytics-sync", owner="lena.k", action="export.start", resource="p", outcome="ok",
                 source="relay-ops-host", at=(T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return "\n".join(json.dumps(r) for r in t.records) + "\n"


def test_relay_automation_off_suppresses_and_on_cannot_trip_without_a_registry(tmp_path, capsys, monkeypatch):
    off = {r["rule"]: r["done"] for r in run(tmp_path, capsys, monkeypatch, automation="off", trail=trail_lines())}
    assert off["DR-001"][0] == "page:security-oncall:automation-suppressed"
    on = {r["rule"]: r["done"] for r in run(tmp_path, capsys, monkeypatch, trail=trail_lines())}
    assert on["DR-001"][0] == "page:security-oncall:automation-unavailable"  # never a phantom trip


def test_a_router_without_a_trip_function_never_records_a_trip():
    routing = load_json(ROOT / "infra/monitoring/routing.json")
    router = Router(routing)
    done = router.dispatch(AlertRecord("a", "DR-001", T0, "page", "security", "x", (), "agent"),
                           Pager(routing["receivers"]))
    assert done[0] == "page:security-oncall:automation-unavailable" and router.automated == []


class Ok:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_pager_client_groups_repeats_by_reusing_the_deduplication_key():
    keys = []
    client = PagerClient("https://events.pager.example/v2/enqueue", {"security-oncall": "rk"}, group_minutes=60,
                         opener=lambda req, timeout: (keys.append(json.loads(req.data)["dedup_key"]), Ok())[1])
    for i, minutes in enumerate((0, 10, 61)):
        at = T0 + timedelta(minutes=minutes)
        client.page(AlertRecord(f"SD-002:{i}", "SD-002", at, "page", "security", "x", ()), "security-oncall", at)
    assert keys == ["SD-002:0", "SD-002:0", "SD-002:2"]


def test_grouping_survives_between_one_shot_runs(tmp_path):
    keys = []

    def opener(req, timeout):
        keys.append(json.loads(req.data)["dedup_key"])
        return Ok()
    state = str(tmp_path / "pager-state.json")
    for i, minutes in enumerate((0, 30)):  # two separate monitor runs, each with a new client
        client = PagerClient("https://events.pager.example/v2/enqueue", {"security-oncall": "rk"}, group_minutes=60,
                             opener=opener, state_path=state)
        at = T0 + timedelta(minutes=minutes)
        client.page(AlertRecord(f"SD-002:{i}", "SD-002", at, "page", "security", "x", ()), "security-oncall", at)
    assert keys == ["SD-002:0", "SD-002:0"]
