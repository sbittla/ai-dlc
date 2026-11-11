"""Deployed detection, routing and paging (4.27.0, ADR-038): agent-detection-v1 over the audit trail, the service
rules over security events, and delivery that follows Relay's on-call policy. Fixtures are small and hand-checked."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from relay.audit import AuditTrail
from relay.telemetry import detection
from relay.telemetry.alerting import AlertRecord, Pager, Router, from_detection, load_json, operational_alerts
from relay.telemetry.monitor import Monitor

ROOT = Path(__file__).resolve().parent.parent
AGENT_RULES = detection.load_rules(ROOT / "infra/detection/rules.json")
SERVICE_RULES = detection.load_rules(ROOT / "infra/detection/service-rules.json")
ROUTING = load_json(ROOT / "infra/monitoring/routing.json")
T0 = datetime(2027, 2, 18, 14, 0, tzinfo=timezone.utc)


def stamp(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def trail_with(exports_at, baseline_days=2, source="relay-nonprod-vpc"):
    """A trail: one export a day for `baseline_days` before T0, then exports at the given minutes after T0."""
    t = AuditTrail(clock=lambda: stamp(0))
    for day in range(baseline_days, 0, -1):
        t.append(agent_id="analytics-sync", owner="lena.k", action="export.start", resource="project:usage",
                 outcome="ok", source="relay-ops-host", at=stamp(-day * 1440))
    for m in exports_at:
        t.append(agent_id="analytics-sync", owner="lena.k", action="export.start", resource="project:usage",
                 outcome="ok", source=source, at=stamp(m))
    return t.records


def test_the_rule_set_deployed_is_chapter_14s_unchanged():
    assert AGENT_RULES["version"] == "agent-detection-v1"
    assert [r["id"] for r in AGENT_RULES["rules"]] == ["DR-001", "DR-002", "DR-003", "DR-004"]
    assert SERVICE_RULES["version"] == "relay-service-detection-v1"


def test_dr001_export_burst_and_dr002_new_network_fire_with_evidence():
    records = trail_with([1, 2, 3, 4], source="as-64500")
    events = detection.from_trail(records)
    baseline = detection.build_baseline([e for e in events if e.at < T0], AGENT_RULES)
    alerts = detection.evaluate([e for e in events if e.at >= T0], AGENT_RULES, baseline)
    by_rule = {a.rule: a for a in alerts}
    # DR-001: threshold max(3, 3 x 1) = 3; the fourth export in the hour exceeds it at 14:04, alerted at 14:05.
    assert (by_rule["DR-001"].value, by_rule["DR-001"].threshold) == (4, 3)
    assert by_rule["DR-001"].alert_at == T0 + timedelta(minutes=5)
    assert by_rule["DR-001"].evidence == ("trail:3", "trail:4", "trail:5", "trail:6")
    # DR-002: the first export from a network the identity never used, alerted at the first boundary after 14:01.
    assert by_rule["DR-002"].alert_at == T0 + timedelta(minutes=5) and by_rule["DR-002"].evidence == ("trail:3",)


def test_a_tampered_trail_is_an_alert_not_an_input():
    records = trail_with([1, 2, 3, 4])
    records[3] = {**records[3], "resource": "project:other"}  # edited without recomputing the hash
    monitor = Monitor({}, {"rules": []}, Router(ROUTING), Pager(ROUTING["receivers"]))
    alerts = monitor.trail_alerts(records, AGENT_RULES, detection.Baseline({}, {}), now=T0)
    assert [a.rule for a in alerts] == ["TRAIL-TAMPER"] and "hash mismatch at record 4" in alerts[0].summary


def security_events(failures_by_minute, success_at=None, network="198.51.100.0/24"):
    rows = []
    for minute, n in failures_by_minute.items():
        rows += [{"at": stamp(minute + i / 1000), "event": "auth.failure", "network": network,
                  "credential": f"fp{minute}-{i}"} for i in range(n)]
    if success_at is not None:
        rows.append({"at": stamp(success_at), "event": "auth.success", "network": network, "credential": "fp-ok"})
    return detection.from_security_events(sorted(rows, key=lambda r: r["at"]))


def test_service_rules_catch_a_credential_stuffing_burst():
    events = security_events({1: 150, 2: 150}, success_at=3)
    baseline = detection.build_baseline([], SERVICE_RULES)
    alerts = {a.rule: a for a in detection.evaluate(events, SERVICE_RULES, baseline)}
    assert alerts["SD-001"].value == 201 and alerts["SD-001"].threshold == 200  # the 201st failure in 5 minutes
    assert alerts["SD-002"].value == 21 and alerts["SD-002"].group == "198.51.100.0/24"
    assert alerts["SD-003"].value == 300 and alerts["SD-003"].alert_at == T0 + timedelta(minutes=5)


def test_routing_follows_the_rules_response():
    router = Router(ROUTING)
    pager = Pager(ROUTING["receivers"])
    tripped = []
    dr001 = AlertRecord("a1", "DR-001", T0, "page", "security", "export burst", ("trail:6",), "analytics-sync")
    assert router.dispatch(dr001, pager, lambda g, actor, why: tripped.append((g, actor))) == [
        "automation:killswitch", "page:security-oncall"]
    assert tripped == [("analytics-sync", "detection:DR-001")]
    assert pager.notifications == [(T0, "security-lead", "a1")]  # the security lead hears at once
    dr002 = AlertRecord("a2", "DR-002", T0, "page", "security", "new network", (), "eval-harvester")
    assert router.dispatch(dr002, pager) == ["page:security-oncall"]


def test_the_automation_switch_turns_every_trip_into_a_page():
    router = Router(ROUTING, automation_enabled=False)
    pager = Pager(ROUTING["receivers"])
    alert = AlertRecord("a1", "DR-003", T0, "page", "security", "read volume", (), "dataset-refresh")
    assert router.dispatch(alert, pager, lambda *a: (_ for _ in ()).throw(AssertionError("tripped"))) == [
        "page:security-oncall:automation-suppressed", "page:security-oncall"]
    assert router.suppressed == [(T0, "DR-003", "dataset-refresh")]


def test_automation_is_rate_limited_to_three_actions_an_hour():
    router, pager = Router(ROUTING), Pager(ROUTING["receivers"])
    done = [router.dispatch(AlertRecord(f"a{i}", "DR-001", T0 + timedelta(minutes=i), "page", "security", "x", (),
                                        f"agent-{i}"), pager, lambda *a: None)[0] for i in range(4)]
    assert done == ["automation:killswitch"] * 3 + ["page:security-oncall:automation-suppressed"]


def test_pages_escalate_at_10_and_20_minutes_unless_acknowledged():
    pager = Pager(ROUTING["receivers"])
    a = AlertRecord("p1", "SLO-API-LATENCY", T0, "page", "reliability", "burn", ())
    b = AlertRecord("p2", "AL-001", T0, "page", "reliability", "stall", ())
    pager.page(a, "platform-oncall", T0)
    pager.page(b, "platform-oncall", T0)
    pager.ack("p2", "oncall", T0 + timedelta(minutes=4))
    pager.advance(T0 + timedelta(minutes=25))
    assert pager.pages[0].escalations == [(T0 + timedelta(minutes=10), "secondary-oncall"),
                                          (T0 + timedelta(minutes=20), "engineering-manager")]
    assert pager.pages[1].escalations == []


def test_al001_runtime_check_for_esc_ac29_a_stopped_evaluator_pages_after_5_minutes():
    """ESC-AC29 is outside ESC-SPEC-1 1.2.0, a runtime check; this tests AL-001, which implements it."""
    rules = load_json(ROOT / "infra/monitoring/alerts.json")
    assert operational_alerts(rules, {"relay.worker.heartbeat_age": 300.0}, T0) == []
    alert, = operational_alerts(rules, {"relay.worker.heartbeat_age": 301.0}, T0)
    assert (alert.rule, alert.severity) == ("AL-001", "page")
    assert Router(ROUTING).receivers_for(alert) == ["platform-oncall"]


def test_cannot_evaluate_budget_stops_and_unknown_outcomes_open_tickets():
    rules = load_json(ROOT / "infra/monitoring/alerts.json")
    alerts = operational_alerts(rules, {"relay.escalation.cannot_evaluate.1h": 2,
                                        "relay.agent.budget_stops.1h": {"spec-to-pr-helper": 1},
                                        "relay.agent.unknown_outcome.1h": {"spec-to-pr-helper": 0}}, T0)
    assert [(a.rule, a.severity, a.group) for a in alerts] == [("AL-002", "ticket", ""),
                                                              ("AL-004", "ticket", "spec-to-pr-helper")]
    assert Router(ROUTING).receivers_for(alerts[1]) == ["agent-owner-tickets"]


def test_detection_alerts_become_pages_and_the_monitor_sends_each_once():
    a = detection.Alert("DR-002", "eval-harvester", T0, T0, 1, 0, "medium", ("trail:9",))
    record = from_detection(a)
    assert (record.severity, record.category, record.evidence) == ("page", "security", ("trail:9",))
    pager = Pager(ROUTING["receivers"])
    monitor = Monitor({}, {"rules": []}, Router(ROUTING), pager)
    assert len(monitor.tick(T0, alerts=[record])) == 1 and monitor.tick(T0, alerts=[record]) == []
    assert len(pager.pages) == 1


def test_every_alert_rule_has_a_runbook_and_a_route():
    rules = json.loads((ROOT / "infra/monitoring/alerts.json").read_text(encoding="utf-8"))["rules"]
    router = Router(ROUTING)
    for rule in rules:
        assert (ROOT / rule["runbook"]).is_file(), rule["id"]
        record = AlertRecord("x", rule["id"], T0, rule["severity"], rule["category"], "", ())
        assert all(r in ROUTING["receivers"] for r in router.receivers_for(record))
    assert set(ROUTING["automation"]["allowed_rules"]) == {"DR-001", "DR-003"}


def test_repeat_alerts_for_one_rule_join_the_open_page_for_an_hour():
    pager = Pager(ROUTING["receivers"], ROUTING["grouping"]["minutes"])
    for i, minutes in enumerate((0, 5, 59, 61)):
        pager.page(AlertRecord(f"s{i}", "SD-002", T0 + timedelta(minutes=minutes), "page", "security", "x", ()),
                   "security-oncall", T0 + timedelta(minutes=minutes))
    assert len(pager.pages) == 2 and pager.pages[0].grouped == ["s1", "s2"]
