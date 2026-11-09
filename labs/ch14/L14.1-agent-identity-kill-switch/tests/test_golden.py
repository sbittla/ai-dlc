"""Golden tests: every number Chapter 14 quotes from Lab 14.1. A change that moves one must fail here."""

from collections import Counter
from datetime import date

from conftest import DATA_DIR

from agentsec.inventory import check_inventory, gate_status, load_json
from agentsec.report import (detection, render_detect, render_drill, render_identities, render_incident,
                             render_privacy, render_replace, render_scoping, render_trail, seeded_results)
from conftest import POLICY

BEFORE = DATA_DIR / "identities" / "inventory-2026-12-14.json"
AFTER = DATA_DIR / "identities" / "inventory-2027-01-12.json"


def test_inventory_before_the_change():
    findings = check_inventory(load_json(BEFORE), POLICY, date(2026, 12, 14))
    assert len(findings) == 27 and gate_status(findings) == 1
    assert Counter(f.severity for f in findings) == {"critical": 1, "high": 11, "medium": 15}
    assert Counter(f.rule for f in findings) == {"IDN001": 3, "IDN002": 2, "IDN003": 2, "IDN004": 1, "IDN005": 4,
                                                 "IDN006": 3, "IDN008": 5, "IDN009": 6, "IDN010": 1}
    assert Counter(f.credential for f in findings) == {"C01": 7, "C02": 8, "C03": 2, "C04": 3, "C05": 1, "C06": 5,
                                                       "break-glass": 1}
    text, status = render_identities(BEFORE, date(2026, 12, 14))
    assert "Credentials: 6; agents: 5; findings: 27 (critical 1, high 11, medium 15); gate exit 1" in text
    assert "Credentials with no expiry: 3" in text
    assert "| IDN004 | C02 | ci-failure-triage | critical | can approve (counts toward required reviews) and merge |" \
        in text


def test_inventory_after_the_change():
    text, status = render_identities(AFTER, date(2027, 1, 12))
    assert "Credentials: 13; agents: 6; findings: 0 (critical 0, high 0, medium 0); gate exit 0" in text
    assert status == 0


def test_detection_replay():
    rules, baseline, base_ev, eval_ev, truth, alerts = detection()
    assert (len(base_ev), len(eval_ev), truth.count("attacker")) == (1577, 1330, 55)
    rule = {r["id"]: r for r in rules["rules"]}
    assert [baseline.threshold(rule[r], i) for r in ("DR-001", "DR-003") for i in ("svc-0417", "svc-0388")] == [
        3, 9, 4200, 26931]
    text = render_detect(False)
    assert "Alerts: 17 (16 on misuse, 1 false alarm). On misuse by rule: DR-001 1, DR-002 11, DR-003 4." in text
    assert "First DR-002 alert on misuse: 2026-11-23 19:45:00 UTC, 2 min 50 s after the first misuse." in text
    assert "First DR-001 alert on misuse: 2026-11-23 19:50:00 UTC, 7 min 50 s after the first misuse." in text
    assert "First DR-003 alert on misuse: 2026-11-23 20:05:00 UTC, 22 min 50 s after the first misuse." in text
    assert "Days with misuse exports: 14; days with at least one alert: 11." in text
    assert "| 2026-12-07 10:18:00 | 10:20:00 | DR-001 | svc-0388 | 10 | 9 | analytics-backfill |" in text
    assert "| 2026-11-23 20:01:00 | 20:05:00 | DR-003 | svc-0417 | 4,530 | 4,200 | attacker |" in text
    assert "| 2026-11-23 19:45:30 | 19:50:00 | DR-001 | svc-0417 | 4 | 3 | attacker |" in text
    assert "Replay window: 49 d 10 h, 7 weeks: 28 d of baseline, 21 d 10 h evaluated." in text


def test_seeded_detection_cases():
    rules, baseline, *_ = detection()
    assert {r["id"]: (r["fired"], r["outcome"]) for r in seeded_results(rules, baseline)} == {
        "D01": ([], "missed"), "D02": (["DR-003"], "detected"), "D03": ([], "clean (control)"),
        "D04": (["DR-002"], "detected")}


def test_incident_figures():
    text = render_incident()
    assert "Reported: 2026-12-14 09:10:00 UTC, 20 d 13 h 27 min 50 s after the first misuse; P1 declared 09:30." in text
    assert "First night: first call tickets.list at 19:42:10; 5 export jobs started 19:44-19:46; downloaded 19:58-20:04 UTC."         in text
    assert "Later misuse: 13 more days, every call between 01:00 and 05:00 UTC." in text
    assert ("Token revoked: 2026-12-14 09:52:00 UTC, 42 min after the report and 20 d 14 h 9 min 50 s after the "
            "first misuse.") in text
    assert "Misuse: 55 calls, 21 export jobs on 14 days, 57,958 task rows downloaded." in text
    assert "Tickets exposed (largest export of each project): 19,432 in 6 projects; requesters in them: 7,412." in text
    assert "First misuse: 2026-11-23 19:42:10 UTC, from as-64500. Last misuse: 2026-12-12 03:50:59 UTC." in text


def test_audit_trail_figures():
    text = render_trail()
    assert "Records: 641; agents: 6; anchors: 124; chain and anchors: ok." in text
    assert "Attributed to an agent, its owner and a person: 641 of 641." in text
    assert "Token exchanges: 209; kill-switch trips: 2; restores: 2; refused calls: 2." in text
    assert "Before 4.23.0 (request log, 2,907 events): 0 name an agent, 0 name a person." in text
    assert "| T1-edited-record | 641 | hash mismatch at seq 200 | hash mismatch at seq 200 |" in text
    assert "| T2-deleted-record | 640 | sequence gap at seq 301 | sequence gap at seq 301 |" in text
    assert "| T3-truncated-tail | 521 | ok | truncated after anchor at seq 524 |" in text
    assert "| T4-edited-and-rehashed | 641 | ok | anchor mismatch at seq 203 |" in text


def test_drills():
    text = render_drill()
    assert "| DRILL-1 | eval-harvester | 300 s | 210 s | 29 s | disabled | FAIL |" in text
    assert "the trip comes 4 s after the alert (assumed)" in text
    assert "- github: revoke relay-agents installation tokens issued to coding-session and suspend the installation" in text
    assert "- aws: set desired count 0 on ECS services tagged agent=coding-session, then stop its running tasks" in text
    assert "| DRILL-2 | eval-harvester | 0 s | 4 s | 29 s | disabled | pass |" in text
    assert "| DRILL-3 | coding-session | 0 s | 6 s | 51 s | disabled | pass |" in text


def test_scoping():
    text = render_scoping()
    assert "| Lab 3.2 as built | 97 | 97 | 350 | 87 | none | mcp-stdio |" in text
    assert "| Lab 14.1 scoped | 97 | 55 | 200 | 0 | out_of_scope 39, row_budget_exhausted 3 | coding-session for " \
           "priya.n |" in text


def test_privacy_redaction_of_the_debug_log():
    text = render_privacy()
    assert "Replaced: auth-header 1, email 6, phone 6, relay-token 1; total 14." in text
    assert "rly_live_" not in text and "@example" not in text


def test_listing_14_2_is_record_200_of_the_trail():
    import json
    lines = (DATA_DIR / "audit" / "agent-trail-2027-01-04_2027-01-10.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[199])
    assert {k: rec[k] for k in ("seq", "at", "agent_id", "owner", "on_behalf_of", "credential", "action", "resource",
                                "outcome", "source", "detail")} == {"seq": 200, "at": "2027-01-05T13:42:00Z", "agent_id": "coding-session", "owner": "sam.o", "on_behalf_of": "priya.n", "credential": "8847d9bcd9b123f5", "action": "token.exchange", "resource": "agent:coding-session", "outcome": "ok", "source": "relay-nonprod-sandbox", "detail": {"scopes": ["tasks:read:platform", "testdb:query"], "ttl_seconds": 900}}
    assert (rec["prev"][:8], rec["hash"][:8]) == ("69193ddf", "26a07596")


def test_replacing_a_static_key():
    text = render_replace("C06", "analytics-sync")
    assert "Before: lifetime none, stored file; 5 findings (IDN001, IDN005, IDN006, IDN008, IDN009)." in text
    assert "After: relay-agent-token, 900 s, stored none, subject " \
        "arn:aws:sts::111122223333:assumed-role/relay-nonprod-agent-analytics-sync; 0 findings." in text
