"""Command-line reports for Lab 14.1 (provided). Run from starter/ or solution/:

    python -m agentsec.report identities ../data/identities/inventory-2026-12-14.json --as-of 2026-12-14 --gate
    python -m agentsec.report detect [--seeded]
    python -m agentsec.report incident
    python -m agentsec.report trail
    python -m agentsec.report drill
    python -m agentsec.report scoping
    python -m agentsec.report privacy

Every number the chapter quotes from this lab is printed by one of these commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta

from relay.audit import AgentRegistry, TokenService, AUDIENCE, redact
from relaymcp.db import open_readonly
from relaymcp.policy import AuditLog, handle

from . import DATA, LAB_ROOT, RELAY
from .detect import build_baseline, evaluate, load_events, load_rules, parse_time, split
from .drill import judge, load_drills, run_drill
from .inventory import (check_attribution, check_credential, check_drills, check_federation, check_inventory,
                        gate_status, load_json, replace_static_key)
from .scoping import ScopedTool, workspace_of
from relaymcp.policy import validate_request
from .trailcheck import attribution, load_anchors, load_trail, replay_attribution, verify_with_anchors

REPLAY = DATA / "activity" / "replay-2026-10-26_2026-12-14.jsonl"
RULES = RELAY / "infra" / "detection" / "rules.json"
REGISTRY = RELAY / "governance" / "agents.json"
TRAIL = DATA / "audit" / "agent-trail-2027-01-04_2027-01-10.jsonl"


def hm(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def span(seconds: float) -> str:
    s = int(round(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = [f"{d} d"] * bool(d) + [f"{h} h"] * bool(h) + [f"{m} min"] * bool(m) + [f"{s} s"] * bool(s or not (d or h or m))
    return " ".join(parts)


# ----------------------------------------------------------------------------- identities

def render_identities(path, as_of: date) -> tuple[str, int]:
    inv = load_json(path)
    policy = load_json(DATA / "identities" / "identity-policy.json")
    findings = check_inventory(inv, policy, as_of)
    sev = Counter(f.severity for f in findings)
    status = gate_status(findings)
    lines = [f"# Credential inventory: {path.name} (as of {as_of.isoformat()})", "",
             f"Credentials: {len(inv['credentials'])}; agents: {len({c['agent'] for c in inv['credentials']})}; "
             f"findings: {len(findings)} (critical {sev['critical']}, high {sev['high']}, medium {sev['medium']}); "
             f"gate exit {status}", "",
             "| Rule | Credential | Agent | Severity | Finding |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {f.rule} | {f.credential} | {f.agent} | {f.severity} | {f.message} |" for f in findings]
    by_rule = Counter(f.rule for f in findings)
    lines += ["", "By rule: " + (", ".join(f"{r} {n}" for r, n in sorted(by_rule.items())) or "none")]
    long_lived = sum(1 for c in inv["credentials"] if c["lifetime_seconds"] is None)
    lines.append(f"Credentials with no expiry: {long_lived}")
    return "\n".join(lines), status


def credential_findings(c: dict, inv: dict, policy: dict, as_of: date) -> list:
    return (check_credential(c, inv, policy) + check_federation(c, policy) + check_attribution(c, policy)
            + check_drills(c, inv, policy, as_of))


def render_replace(cred_id: str, agent_id: str) -> str:
    """Replace one static credential from the 14 December inventory with a registered agent token."""
    policy = load_json(DATA / "identities" / "identity-policy.json")
    before_inv = load_json(DATA / "identities" / "inventory-2026-12-14.json")
    after_inv = load_json(DATA / "identities" / "inventory-2027-01-12.json")
    old = next(c for c in before_inv["credentials"] if c["id"] == cred_id)
    new = replace_static_key(old, AgentRegistry.load(REGISTRY).get(agent_id), f"{cred_id}-R")
    f_old = credential_findings(old, before_inv, policy, date(2026, 12, 14))
    f_new = credential_findings(new, after_inv, policy, date(2027, 1, 12))
    return chr(10).join([
        f"# Replacing {cred_id} ({old['type']}, {old['agent']})", "",
        f"Before: lifetime {old['lifetime_seconds'] or 'none'}, stored {old['stored']}; {len(f_old)} findings ("
        + ", ".join(f.rule for f in f_old) + ").",
        f"After: {new['type']}, {new['lifetime_seconds']} s, stored {new['stored']}, subject {new['trust_subject']}; "
        f"{len(f_new)} findings."])


# ----------------------------------------------------------------------------- detection

def detection(path=REPLAY):
    events, truth = load_events(path)
    rules = load_rules(RULES)
    manifest = load_json(DATA / "activity" / "manifest.json")
    b0, b1 = parse_time(manifest["baseline"]["from"]), parse_time(manifest["baseline"]["to"])
    e0, e1 = parse_time(manifest["evaluate"]["from"]), parse_time(manifest["evaluate"]["to"])
    base_ev, _ = split(events, truth, b0, b1)
    eval_ev, eval_truth = split(events, truth, e0, e1)
    baseline = build_baseline(base_ev, rules)
    alerts = evaluate(eval_ev, rules, baseline)
    return rules, baseline, base_ev, eval_ev, eval_truth, alerts


def render_detect(seeded: bool) -> str:
    rules, baseline, base_ev, eval_ev, truth, alerts = detection()
    rule = {r["id"]: r for r in rules["rules"]}
    manifest = load_json(DATA / "activity" / "manifest.json")
    b0, b1 = parse_time(manifest["baseline"]["from"]), parse_time(manifest["baseline"]["to"])
    e0, e1 = parse_time(manifest["evaluate"]["from"]), parse_time(manifest["evaluate"]["to"])
    misuse = [e for e, t in zip(eval_ev, truth) if t == "attacker"]
    first = misuse[0].at
    true_alerts = [a for a in alerts if truth[a.index] == "attacker"]
    false_alerts = [a for a in alerts if truth[a.index] != "attacker"]
    lines = ["# Detection replay: agent-detection-v1 on reconstructed activity (GENERATED; patterns configured)", "",
             f"Baseline: {len(base_ev)} events, 2026-10-26 to 2026-11-22. Evaluated: {len(eval_ev)} events, "
             f"2026-11-23 to 2026-12-14 10:00 UTC, {len(misuse)} of them the leaked token's misuse.",
             f"Replay window: {span((e1 - b0).total_seconds())}, {round((e1 - b0).days / 7)} weeks: "
             f"{span((b1 - b0).total_seconds())} of baseline, {span((e1 - e0).total_seconds())} evaluated.",
             f"Thresholds for svc-0417: DR-001 more than {baseline.threshold(rule['DR-001'], 'svc-0417')} export starts "
             f"in an hour; DR-003 more than {baseline.threshold(rule['DR-003'], 'svc-0417'):,} rows in an hour.",
             f"Thresholds for svc-0388: DR-001 more than {baseline.threshold(rule['DR-001'], 'svc-0388')} export starts "
             f"in an hour; DR-003 more than {baseline.threshold(rule['DR-003'], 'svc-0388'):,} rows in an hour.", "",
             "| Triggered at (UTC) | Alert at | Rule | Identity | Value | Threshold | Triggered by |",
             "| --- | --- | --- | --- | ---: | ---: | --- |"]
    for a in alerts:
        lines.append(f"| {hm(a.triggered_at)} | {a.alert_at:%H:%M:%S} | {a.rule} | {a.identity} | {a.value:,} | {a.threshold:,} | "
                     f"{truth[a.index]} |")
    per_rule = Counter(a.rule for a in true_alerts)
    lines += ["", f"Alerts: {len(alerts)} ({len(true_alerts)} on misuse, {len(false_alerts)} false alarm"
                  f"{'s' if len(false_alerts) != 1 else ''}). On misuse by rule: "
                  + ", ".join(f"{r} {n}" for r, n in sorted(per_rule.items())) + "."]
    for rid in ("DR-002", "DR-001", "DR-003"):
        firsts = [a for a in true_alerts if a.rule == rid]
        if firsts:
            lines.append(f"First {rid} alert on misuse: {hm(firsts[0].alert_at)} UTC, "
                         f"{span((firsts[0].alert_at - first).total_seconds())} after the first misuse.")
    nights = sorted({e.at.date() for e in misuse if e.action == "export.start"})
    alerted_nights = sorted({eval_ev[a.index].at.date() for a in true_alerts})
    lines.append(f"Days with misuse exports: {len(nights)}; days with at least one alert: {len(alerted_nights)}.")
    if seeded:
        lines += ["", render_seeded(rules, baseline)]
    return "\n".join(lines)


def seeded_results(rules, baseline) -> list[dict]:
    manifest = load_json(DATA / "activity" / "manifest.json")
    out = []
    for case in manifest["seeded"]:
        events, _ = load_events(DATA / "activity" / "seeded" / f"{case['id']}.jsonl")
        fired = sorted({a.rule for a in evaluate(events, rules, baseline)})
        if case["kind"] == "benign":
            outcome = "clean (control)" if not fired else "false alarm"
        else:
            outcome = "detected" if fired else "missed"
        out.append({**case, "fired": fired, "outcome": outcome})
    return out


def render_seeded(rules, baseline) -> str:
    rows = seeded_results(rules, baseline)
    lines = ["| Case | Seeded change | Expected | Fired | Result |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['id']} | {r['change']} | {', '.join(r['expected']) or 'none'} | "
                     f"{', '.join(r['fired']) or 'none'} | {r['outcome']} |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- incident

def render_incident() -> str:
    tl = load_json(DATA / "incident" / "timeline.json")
    rules, baseline, base_ev, eval_ev, truth, alerts = detection()
    misuse = [e for e, t in zip(eval_ev, truth) if t == "attacker"]
    first, last = misuse[0].at, misuse[-1].at
    reported = parse_time(tl["reported"])
    revoked = parse_time(tl["token_revoked"])
    starts = [e for e in misuse if e.action == "export.start"]
    downloads = [e for e in misuse if e.action == "export.download"]
    largest = {}
    for e in downloads:
        project = e.resource.rsplit(":", 1)[1]
        largest[project] = max(largest.get(project, 0), e.rows)
    true_alerts = [a for a in alerts if truth[a.index] == "attacker"]
    night = [e for e in misuse if e.at.date() == first.date()]
    night_starts = [e for e in night if e.action == "export.start"]
    night_dl = [e for e in night if e.action == "export.download"]
    later = [e for e in misuse if e.at.date() > first.date()]
    lines = ["# The leaked token (composite; GENERATED data)", "",
             f"Token printed in a CI debug log: {tl['leaked']}; posted in a public issue: {tl['posted_publicly']}.",
             f"First misuse: {hm(first)} UTC, from {tl['attacker_source']}. Last misuse: {hm(last)} UTC.",
             f"First night: first call {misuse[0].action} at {first:%H:%M:%S}; {len(night_starts)} export jobs started "
             f"{night_starts[0].at:%H:%M}-{night_starts[-1].at:%H:%M}; downloaded {night_dl[0].at:%H:%M}-"
             f"{night_dl[-1].at:%H:%M} UTC.",
             f"Later misuse: {len({e.at.date() for e in later})} more days, every call between "
             f"{min(e.at.hour for e in later):02d}:00 and {max(e.at.hour for e in later) + 1:02d}:00 UTC.",
             f"Reported: {hm(reported)} UTC, {span((reported - first).total_seconds())} after the first misuse; "
             f"P1 declared {parse_time(tl['p1_declared']):%H:%M}.",
             f"Token revoked: {hm(revoked)} UTC, {span((revoked - reported).total_seconds())} after the report and "
             f"{span((revoked - first).total_seconds())} after the first misuse.",
             f"Misuse: {len(misuse)} calls, {len(starts)} export jobs on {len({e.at.date() for e in starts})} days, "
             f"{sum(e.rows for e in downloads):,} task rows downloaded.",
             f"Tickets exposed (largest export of each project): {sum(largest.values()):,} in {len(largest)} projects; "
             f"requesters in them: {tl['support_workspace']['distinct_requesters_in_exported_projects']:,}.",
             f"With agent-detection-v1: first alert {hm(true_alerts[0].alert_at)} UTC "
             f"({true_alerts[0].rule}), {span((true_alerts[0].alert_at - first).total_seconds())} after the first misuse."]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- trail

def render_trail() -> str:
    registry = AgentRegistry.load(REGISTRY)
    records = load_trail(TRAIL)
    anchors = load_anchors(DATA / "audit" / "anchors.json")
    v = verify_with_anchors(records, anchors)
    att = attribution(records, registry)
    actions = Counter(r["action"] for r in records)
    raw = [json.loads(line) for line in REPLAY.read_text(encoding="utf-8").splitlines() if line.strip()]
    events, _ = load_events(REPLAY)
    n, agent, person = replay_attribution(events, raw)
    lines = ["# Audit trail of agent actions, 4-10 January 2027 (GENERATED with relay.audit)", "",
             f"Records: {len(records)}; agents: {len({r['agent_id'] for r in records})}; anchors: {len(anchors)}; "
             f"chain and anchors: {'ok' if v.ok else v.problem + ' at seq ' + str(v.seq)}.",
             f"Attributed to an agent, its owner and a person: {att.attributed} of {att.records}.",
             f"Token exchanges: {actions['token.exchange']}; kill-switch trips: {actions['killswitch.trip']}; "
             f"restores: {actions['killswitch.restore']}; refused calls: "
             f"{sum(1 for r in records if r['outcome'] not in ('ok',))}.",
             f"Before 4.23.0 (request log, {n:,} events): {agent} name an agent, {person} name a person.", "",
             "| Copy | Records | Chain only | Chain and anchors |", "| --- | ---: | --- | --- |"]
    for path in sorted((DATA / "audit" / "tampered").glob("*.jsonl")):
        recs = load_trail(path)
        chain = verify_with_anchors(recs, [])
        full = verify_with_anchors(recs, anchors)
        fmt = lambda x: "ok" if x.ok else f"{x.problem} at seq {x.seq}"  # noqa: E731
        lines.append(f"| {path.stem} | {len(recs)} | {fmt(chain)} | {fmt(full)} |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- drill

def render_drill() -> str:
    drills = load_drills(DATA / "drill" / "drills.json")
    assumptions = load_json(DATA / "drill" / "assumptions.json")
    req = drills["requirement_seconds"]
    lines = [f"# Kill-switch drills (simulated agents; Relay's side in process; cloud side ASSUMED). "
             f"Requirement: {req} s from alert", "",
             "| Drill | Agent | Gateway cache | Time to revoke, Relay (simulated) | Cloud and GitHub (assumed) "
             "| New token after trip | Result |",
             "| --- | --- | ---: | ---: | ---: | --- | --- |"]
    for d in drills["drills"]:
        run = run_drill(d, assumptions, REGISTRY)
        r = judge(run, d, assumptions, req)
        relay = "never in the window" if r.relay_seconds is None else f"{r.relay_seconds:g} s"
        lines.append(f"| {r.drill_id} | {r.agent} | {r.cache_seconds} s | {relay} | {r.cloud_seconds} s | "
                     f"{r.refresh} | {'pass' if r.passed else 'FAIL'} |")
    lines.append("")
    lines.append(f"Relay's side is simulated: the trip comes {assumptions['alert_to_trip']} s after the alert "
                 f"(assumed), and requests follow the drill plans.")
    for d in drills["drills"][1:]:
        run = run_drill(d, assumptions, REGISTRY)
        lines += ["", f"{run.drill_id} steps after the trip:"] + [f"- {s}" for s in run.switch.external_steps]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- scoping

def scoping_run(scoped: bool) -> tuple[list[dict], list[dict]]:
    registry = AgentRegistry.load(REGISTRY)
    service = TokenService(registry, b"lab14.1-scoping-key-not-a-secret-00000", clock=lambda: 1_799_000_000.0,
                           new_id=lambda: "scoping")
    agent = registry.get("coding-session")
    now = 1_799_000_000.0
    token, _ = service.exchange({"iss": agent.issuer, "sub": agent.subject, "aud": AUDIENCE, "iat": now},
                                ["testdb:query"],
                                subject={"iss": registry.person_issuer, "sub": "priya.n", "aud": AUDIENCE, "iat": now})
    claims = service.verify(token, "testdb:query")
    conn = open_readonly(LAB_ROOT / "vendor" / "relay-test.sql")
    audit = AuditLog()
    tool = ScopedTool(conn, registry, audit)
    requests = [json.loads(line) for line in (DATA / "mcp" / "scoping-replay.jsonl").read_text(encoding="utf-8")
                .splitlines() if line.strip()]
    start = datetime(2027, 1, 6, 15, 0)
    out = []
    for n, r in enumerate(requests):
        now = start + timedelta(seconds=10 * n)
        resp = tool.handle(r["request"], claims, now) if scoped else handle(r["request"], conn, audit,
                                                                              caller="mcp-stdio")
        ws = workspace_of(conn, validate_request(r["request"]))
        out.append({"id": r["id"], "intent": r["intent"], "ok": resp["ok"], "error": resp.get("error"),
                    "rows": resp.get("row_count", 0), "workspace": ws})
    return out, audit.entries


def render_scoping() -> str:
    lines = ["# Caller scoping for Lab 3.2's query tool: a simulated coding session, steered into harvesting", "",
             "| Mode | Requests | Answered | Rows returned | From workspace 2 | Refusals | Audit entries name |",
             "| --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for scoped in (False, True):
        results, entries = scoping_run(scoped)
        refusals = Counter(r["error"] for r in results if not r["ok"])
        callers = sorted({e["caller"] for e in entries})
        lines.append(f"| {'Lab 14.1 scoped' if scoped else 'Lab 3.2 as built'} | {len(results)} | "
                     f"{sum(r['ok'] for r in results)} | {sum(r['rows'] for r in results)} | "
                     f"{sum(r['rows'] for r in results if r['workspace'] == 2)} | "
                     f"{', '.join(f'{k} {v}' for k, v in sorted(refusals.items())) or 'none'} | {', '.join(callers)} |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- privacy

def render_privacy() -> str:
    text = (DATA / "incident" / "debug-log-excerpt.txt").read_text(encoding="utf-8")
    clean, counts = redact(text)
    lines = ["# The debug log excerpt, redacted with relay.audit.redact (FAKE token and addresses)", "",
             "Replaced: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f"; total {sum(counts.values())}.",
             "", "```text", clean.rstrip("\n"), "```"]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lab 14.1 reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("identities")
    p.add_argument("inventory")
    p.add_argument("--as-of", required=True)
    p.add_argument("--gate", action="store_true")
    p = sub.add_parser("detect")
    p.add_argument("--seeded", action="store_true")
    p = sub.add_parser("replace")
    p.add_argument("credential")
    p.add_argument("--agent", required=True)
    for name in ("incident", "trail", "drill", "scoping", "privacy"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "identities":
        from pathlib import Path
        text, status = render_identities(Path(args.inventory), date.fromisoformat(args.as_of))
        print(text)
        return status if args.gate else 0
    if args.cmd == "replace":
        print(render_replace(args.credential, args.agent))
        return 0
    print({"detect": lambda: render_detect(args.seeded), "incident": render_incident, "trail": render_trail,
           "drill": render_drill, "scoping": render_scoping, "privacy": render_privacy}[args.cmd]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
