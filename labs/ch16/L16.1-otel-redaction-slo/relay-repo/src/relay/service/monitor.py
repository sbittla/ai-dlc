"""Run the monitor once over collected telemetry, and page (added in 4.27.0; ADR-038).

    python -m relay.service.monitor --repo . --metrics metrics.jsonl --logs logs.jsonl --trail trail.jsonl \\
        --db relay.db --since 2027-02-18T14:00:00Z --now 2027-02-18T14:30:00Z --dry-run

One run is one evaluation; the gateway task runs it every minute. Each run evaluates:

- the SLOs in `docs/slo/slos.json` over the per-minute SLI counts in `--metrics`;
- the operational rules AL-001 to AL-008 (`infra/monitoring/alerts.json`) over values taken from `--metrics`
  (escalation pass failures, `cannot_evaluate`, agent budget stops and unknown outcomes, overflow), from a leak
  scan of the input files themselves (RF-003, AL-007), and, with `--db`, from the database: the worker's newest
  heartbeat (AL-001, which therefore does not depend on the worker exporting telemetry) and held P1 escalations
  left unacknowledged (AL-006);
- agent-detection-v1 over `--trail` (verified first) and relay-service-detection-v1 over the security events in
  `--logs`, both at five-minute evaluation boundaries, with baselines from the events before `--since`.

With `--dry-run` it writes the alerts as JSON lines on standard output and sends nothing; otherwise it pages
through `PagerClient`, with `RELAY_PAGER_URL` and `RELAY_PAGER_KEYS` from the environment.

Automation: `RELAY_AUTOMATION=off` stops every automated action. When it is on, DR-001 and DR-003 would trip a
kill switch, but this command holds no agent registry (the registry's enabled flags and epochs are still in
memory, ADR-020), so it cannot trip one: it pages the security on-call, recorded `automation-unavailable`, and
the runbook trips the switch. Not here either: escalation and grouping of pages, which the paging provider
does (`PagerClient` reuses a deduplication key for an hour, kept in `--state` between runs); and the weekly RF-001
check (`relay.telemetry.fitness`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from ..escalation import EscalationStore
from ..telemetry import detection
from ..telemetry.alerting import Pager, Router, load_json
from ..telemetry.fitness import held_p1_unacknowledged, telemetry_leak_check
from ..telemetry.monitor import Monitor, minute_of, operational_values, sli_minutes_from_otlp
from ..telemetry.slo import load_slos
from ..worker import TriageQueue
from .pager import PagerClient


def _lines(path: str | None) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines() if path else []


def _at(text: str) -> datetime:
    return detection.parse_time(text)


def values_at(args, now: datetime) -> dict:
    """Every value the operational rules read, from the metrics, the input files and the database."""
    values = operational_values(_lines(args.metrics), now)
    files = [p for p in (args.metrics, args.logs) if p]
    if files:
        values["relay.telemetry.leaks"] = telemetry_leak_check(files).value
    if args.db:
        last = TriageQueue(args.db).last_pass_at()
        values["relay.worker.heartbeat_age"] = float("inf") if last is None else now.timestamp() - last
        store = EscalationStore(args.db)
        values["relay.escalation.p1_held_unacknowledged"] = held_p1_unacknowledged(
            store, [task for task, _ in store.live_tasks()], now)
    return values


def run(args, env) -> list[dict]:
    repo = Path(args.repo)
    routing = load_json(repo / "infra/monitoring/routing.json")
    router = Router(routing, automation_enabled=env.get("RELAY_AUTOMATION", "on").strip().lower() != "off")
    group = routing.get("grouping", {}).get("minutes", 0)
    if args.dry_run:
        send = Pager(routing["receivers"], group)
    else:
        send = PagerClient(env["RELAY_PAGER_URL"], json.loads(env["RELAY_PAGER_KEYS"]), group_minutes=group,
                           state_path=args.state)
    monitor = Monitor(load_slos(repo / "docs/slo/slos.json"), load_json(repo / "infra/monitoring/alerts.json"),
                      router, send)  # no trip function: see the module docstring
    since, now = _at(args.since), _at(args.now)
    records = monitor.slo_alerts(sli_minutes_from_otlp(_lines(args.metrics)), minute_of(int(since.timestamp() * 1e9)),
                                 minute_of(int(now.timestamp() * 1e9)))
    trail = detection.trail_records(_lines(args.trail))
    if trail:
        rules = detection.load_rules(repo / "infra/detection/rules.json")
        before = [e for e in detection.from_trail(trail) if e.at < since]
        records += monitor.trail_alerts(trail, rules, detection.build_baseline(before, rules), now=now, since=since)
    events = detection.from_security_events(detection.security_events_from_otlp(_lines(args.logs)))
    if events:
        rules = detection.load_rules(repo / "infra/detection/service-rules.json")
        baseline = detection.build_baseline([e for e in events if e.at < since], rules)
        records += monitor.event_alerts([e for e in events if since <= e.at <= now], rules, baseline)
    delivered = monitor.tick(now, values=values_at(args, now), alerts=[r for r in records if since <= r.at <= now])
    return [{"alert_id": r.alert_id, "rule": r.rule, "at": r.at.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "severity": r.severity, "category": r.category, "summary": r.summary, "evidence": list(r.evidence),
             "done": done} for r, done in monitor.log if r in delivered]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m relay.service.monitor", description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--metrics")
    ap.add_argument("--logs")
    ap.add_argument("--trail")
    ap.add_argument("--db", help="the shared database, for the worker heartbeat and held P1 escalations")
    ap.add_argument("--since", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--state", help="file that keeps the pager's open deduplication keys between runs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for row in run(args, os.environ):
        sys.stdout.write(json.dumps(row, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
