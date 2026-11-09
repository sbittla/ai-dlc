"""Lab 16.1's reports (provided). Every number Chapter 16 quotes from this lab is printed here.

    python -m slolab.report probes        # 4.23.0's redactor against 4.27.0's, on the probe set
    python -m slolab.report instrument    # the service with telemetry on, and a naive access log, leak-scanned
    python -m slolab.report alerts        # three alerting strategies on 30 days of availability
    python -m slolab.report latency       # the latency SLO, including the opening incident's page
    python -m slolab.report budget        # error budgets and the budget policy's actions
    python -m slolab.report quality       # the AI-quality SLO on online-evaluation counts
    python -m slolab.report pilot         # ESC-AC30 per week, and the evidence for D7's review
    python -m slolab.report agents        # agent runs traced from the journal; AL-004 and AL-005
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from . import LAB_ROOT, RELAY
from .alerts import WORKBOOK, Row, burn_alerts, score, static_alerts
from .budget import budget_status
from .data import manifest, minute_index, pilot, probes, quality_days, start_of, traffic
from .pilot import flood_cap_review, parse, weekly_step_delays
from .probes import score_probes, summary, totals

SIGNIFICANT = 0.02  # an event that spends at least 2% of the 30-day budget, the workbook's fast-page threshold


def out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def clock(start: datetime, minute: int) -> str:
    return (start + timedelta(minutes=minute)).strftime("%m-%d %H:%M")


def labelled(kind: str):
    """The series for an SLO and its labelled events, with significance worked out from the data."""
    doc = manifest()
    start = start_of(doc)
    _, total, errors, slow = traffic()
    bad = errors if kind == "availability" else [e + s for e, s in zip(errors, slow)]
    target = 0.999 if kind == "availability" else 0.99
    allowed = (1 - target) * sum(total)
    events = []
    for ev in doc["events"]:
        if ev["kind"] != kind:
            continue
        a, b = minute_index(start, ev["start"]), minute_index(start, ev["end"])
        share = sum(bad[a:b + 1]) / allowed
        events.append({"id": ev["id"], "title": ev["title"], "start": a, "end": b, "spent": share,
                       "significant": share >= SIGNIFICANT})
    return start, total, bad, target, events


def probes_report() -> dict:
    from relay.audit.redact import redact as old
    from relay.telemetry.redact import redact_text as new
    cases = probes()
    before, after = score_probes(old, cases), score_probes(new, cases)
    out("Redaction probes (data/redaction/probes.jsonl): 4.23.0's relay.audit.redact vs 4.27.0's relay.telemetry")
    out(f"{'category':<14} {'probes':>6}  {'4.23.0 caught':>13}  {'4.27.0 caught':>13}")
    sb, sa = summary(before), summary(after)
    for cat in sb:
        n = sum(sb[cat].values())
        out(f"{cat:<14} {n:>6}  {sb[cat].get('caught', 0) + sb[cat].get('false-positive', 0):>13}  "
            f"{sa[cat].get('caught', 0) + sa[cat].get('false-positive', 0):>13}")
    tb, ta = totals(before), totals(after)
    out(f"sensitive probes: {tb.get('caught', 0) + tb.get('missed', 0)}; caught by 4.23.0 {tb.get('caught', 0)}, "
        f"by 4.27.0 {ta.get('caught', 0)}; false positives {tb.get('false-positive', 0)} and "
        f"{ta.get('false-positive', 0)}")
    missed = [r.probe_id for r in after if r.outcome == "missed"]
    out(f"still missed by 4.27.0 (known misses, pinned): {', '.join(missed)}")
    return {"before": tb, "after": ta, "missed": missed}


def instrument_report() -> dict:
    from .instrument import exercise
    r = exercise(LAB_ROOT / "evidence" / "telemetry")
    out(f"Requests sent: {r['requests']} ({', '.join(f'{k}: {v}' for k, v in r['statuses'].items())})")
    out(f"Exported: {r['spans']} spans, {r['security_events']} security events; routes: {', '.join(r['routes'])}")
    out(f"Dropped or replaced at export: {r['redactions_at_export'] or 'nothing'}")
    out(f"RF-003 on the export: {'PASS' if r['rf003'].passed else 'FAIL'} ({r['rf003'].detail})")
    out(f"RF-004: {'PASS' if r['rf004'].passed else 'FAIL'} ({r['rf004'].detail})")
    out(f"Naive access log of the same requests: {r['naive_total']} findings {r['naive_findings']}")
    return r


def strategies(kind: str = "availability") -> dict:
    start, total, bad, target, events = labelled(kind)
    budget = 1 - target
    results = {
        "static 5 min > budget": static_alerts(bad, total, budget, 5, min_events=100),
        "burn 1 h >= 14.4": burn_alerts(bad, total, target, (Row(60, 60, 14.4, "page"),), min_events=100),
        "multi-window (workbook)": burn_alerts(bad, total, target, WORKBOOK, min_events=100),
    }
    return {"start": start, "events": events, "results": results, "total": total, "bad": bad, "target": target}


def alerts_report(kind: str = "availability") -> dict:
    s = strategies(kind)
    start, events = s["start"], s["events"]
    label = "SLO-API-AVAIL (99.9%)" if kind == "availability" else "SLO-API-LATENCY (99% within 250 ms)"
    out(f"{label}, 30 days from {start:%Y-%m-%d}; events (configured in the generator):")
    for ev in events:
        out(f"  {ev['id']} {clock(start, ev['start'])}-{clock(start, ev['end'])} spent {ev['spent']:.1%} of the "
            f"budget ({'significant' if ev['significant'] else 'not significant'}): {ev['title']}")
    out(f"{'strategy':<26} {'pages':>5} {'false':>5}  detected  missed  detection (min)        reset (min)")
    summary_rows = {}
    for name, found in s["results"].items():
        sc = score(found, events)
        tickets = sum(1 for e in found if e[0] == "ticket")
        det = ", ".join(f"{k} {v}" for k, v in sc.detect_minutes.items())
        rst = ", ".join(f"{k} {v}" for k, v in sc.reset_minutes.items())
        out(f"{name:<26} {sc.episodes:>5} {sc.false_alarms:>5}  {','.join(sc.detected) or '-':<9} "
            f"{','.join(sc.missed) or '-':<7} {det:<22} {rst}")
        if tickets:
            tk = score(found, events, action="ticket")
            out(f"{'':<26} tickets {tickets}: detected {','.join(tk.detected)}; "
                f"first after {', '.join(f'{k} {v} min' for k, v in tk.detect_minutes.items())}")
        summary_rows[name] = (sc, found)
    return {"events": events, "rows": summary_rows, "start": start}


def consistency(kind: str = "availability") -> bool:
    """The lab's multi-window evaluator agrees with Relay's relay.telemetry.slo.evaluate on the same series."""
    from relay.telemetry.slo import SLO, Series, evaluate
    s = strategies(kind)
    good = [t - b for t, b in zip(s["total"], s["bad"])]
    relay_eps = [(e.action, e.start, e.end) for e in evaluate(Series(good, s["total"]), SLO("x", "x", s["target"],
                                                                                         min_events=100))]
    return sorted(relay_eps, key=lambda e: (e[1], e[0])) == s["results"]["multi-window (workbook)"]


def latency_report() -> dict:
    r = alerts_report("latency")
    start = r["start"]
    sc, found = r["rows"]["multi-window (workbook)"]
    e5 = next(ev for ev in r["events"] if ev["id"] == "E5")
    page = next(e for e in found if e[0] == "page" and e[2] >= e5["start"])
    out(f"Opening incident (E5): degradation from {clock(start, e5['start'])}, first page {clock(start, page[1])} "
        f"({page[1] - e5['start']} min later); rollback at 02-02 15:31 changed nothing; page open until "
        f"{clock(start, page[2])}")
    out(f"Lab evaluator agrees with relay.telemetry.slo.evaluate: {consistency('latency')}")
    return {"page": page, "e5": e5}


def budget_report() -> dict:
    res = {}
    for kind in ("availability", "latency"):
        start, total, bad, target, events = labelled(kind)
        b = budget_status(bad, total, target, events)
        name = "SLO-API-AVAIL" if kind == "availability" else "SLO-API-LATENCY"
        out(f"{name}: {b.events:,} requests, {b.bad:,} bad, {b.allowed:,.1f} allowed; remaining {b.remaining:.1%}")
        out("  spent by event: " + ", ".join(f"{k} {v:.1%}" for k, v in b.spent_by_event.items()))
        out(f"  policy actions: {', '.join(b.actions) or 'none'}")
        res[kind] = b
    return res


def quality_report() -> dict:
    from relay.telemetry.slo import SLO, BurnWindow, Series, evaluate
    days = quality_days()
    good, total = [], []
    for _, kept, n in days:  # each day's labels arrive in its last minute
        good += [0] * 1439 + [kept]
        total += [0] * 1439 + [n]
    slo = SLO("SLO-TRIAGE-QUALITY", "", 0.8, min_events=100, policy=(BurnWindow(10080, 1440, 1.5, "ticket"),))
    eps = evaluate(Series(good, total), slo)
    kept, n = sum(d[1] for d in days), sum(d[2] for d in days)
    out(f"SLO-TRIAGE-QUALITY (80% kept unchanged): {kept} of {n} suggestions kept over 30 days ({kept / n:.1%})")
    from relay.telemetry.slo import budget
    b = budget(Series(good, total), slo)
    out(f"  error budget: {b.bad} bad of {b.allowed_bad:.1f} allowed; remaining {b.remaining:.1%}"
        f"{' (exhausted: the budget policy stops triage prompt, model and routing changes)' if b.remaining < 0 else ''}")
    drop = [d for d in days if "2027-01-19" <= d[0] <= "2027-01-25"]
    dk, dn = sum(d[1] for d in drop), sum(d[2] for d in drop)
    out(f"  configured drop, 19-25 January: {dk} of {dn} kept ({dk / dn:.1%})")
    for ep in eps:
        out(f"  ticket from {days[ep.start // 1440][0]} to {days[ep.end // 1440][0]}")
    return {"kept": kept, "n": n, "episodes": [(days[e.start // 1440][0], days[e.end // 1440][0]) for e in eps],
            "drop": (dk, dn)}


def pilot_report() -> dict:
    rows = pilot()
    weeks = weekly_step_delays(rows, parse("2027-01-04T00:00:00Z"))
    out("ESC-AC30 per pilot week (steps fired within 60 s of their due time; at least 95%):")
    for w in weeks:
        out(f"  week {w['week']}: {w['on_time']} of {w['steps']} ({w['share']:.1%}), worst {w['worst_s']} s: "
            f"{'PASS' if w['passed'] else 'FAIL'}")
    d7 = flood_cap_review(rows)
    out(f"D7 flood cap, January pilot: {d7['steps']} steps, {d7['emails']} emails, held by priority {d7['held']}")
    out(f"  target-hours over the cap: {', '.join(d7['target_hours_over_cap'])}")
    for b in d7["bursts"]:
        out(f"    user {b['target']}, {b['hour']}:00: {b['steps']} steps over {b['minutes']} min, {b['priorities']}; "
            f"first acknowledgement {b['first_ack'] or 'none recorded'}")
    out(f"  P1 held: {d7['held_p1']} (targets {d7['held_p1_targets']}); unacknowledged 10 min after: "
        f"{d7['held_p1_unacknowledged_10min']}; their webhook events delivered: {d7['webhooks_for_held_p1']}")
    out(f"  most P1 emails for one target in one hour: {d7['max_p1_per_target_hour']} "
        f"(outside the 21 January outage: {d7['max_p1_per_target_hour_outside_outage']})")
    out(f"  P1 steps acknowledged within 10 minutes: {d7['p1_acknowledged_within_10min']} of {d7['p1_steps']}")
    return {"weeks": weeks, "d7": d7}


def agents_report() -> dict:
    from datetime import timezone
    from relay.telemetry.alerting import load_json, operational_alerts
    from .instrument import agent_traces
    r = agent_traces()
    out(f"Agent runs traced from the journal: {r['runs']} runs, {r['spans']} spans; by status {r['by_status']}")
    out(f"Dropped at export (not on the allowlist): {r['dropped']}")
    from relay.telemetry.runs import run_signals
    from .data import journal
    j = journal()
    rules = load_json(RELAY / "infra" / "monitoring" / "alerts.json")
    alerts = []
    for run in j["runs"]:  # evaluated at the end of the hour each run ended in
        sig = run_signals([run], j["steps"])
        at = datetime.strptime(run["updated_at"][:13], "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
        alerts += operational_alerts(rules, {"relay.agent.budget_stops.1h": sig["relay.agent.budget_stops"],
                                             "relay.agent.unknown_outcome.1h": sig["relay.agent.unknown_outcome"]},
                                     at + timedelta(hours=1))
    for a in alerts:
        out(f"  {a.at:%m-%d %H:%M} {a.rule} ({a.severity}) for {a.group}")
    return {**r, "alerts": [(a.rule, a.severity, a.group) for a in alerts]}


COMMANDS = {"probes": probes_report, "instrument": instrument_report, "alerts": alerts_report,
            "latency": latency_report, "budget": budget_report, "quality": quality_report, "pilot": pilot_report,
            "agents": agents_report}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        out(__doc__)
        return 2
    COMMANDS[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
