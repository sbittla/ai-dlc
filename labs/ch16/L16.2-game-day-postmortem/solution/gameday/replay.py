"""Replays of the 2 February incident and the 18 February game day through Relay 4.27.0's own detection,
SLO, routing and paging code (provided). Both are simulations on generated data; see data/*/ labels.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from relay.telemetry import detection
from relay.telemetry.alerting import AlertRecord, Pager, Router, from_detection, from_episode, load_json
from relay.telemetry.slo import SLO, Series, evaluate

from . import DATA, VENDOR
from .citations import check_hypothesis
from .remediate import Gate, Refused, args_sha256, make_proof
from .store import UTC, Store, parse, read_csv
from .timeline import Entry, fault_measures

CONFIG = VENDOR / "config"
LATENCY = SLO("SLO-API-LATENCY", "", 0.99, min_events=100)


def latency_pages(rows: list[dict]) -> list[AlertRecord]:
    total = [int(r["api_requests"]) for r in rows]
    good = [int(r["api_requests"] - r["api_slow"]) for r in rows]
    start = parse(rows[0]["minute"])
    return [from_episode("SLO-API-LATENCY", ep, lambda i: start + timedelta(minutes=i))
            for ep in evaluate(Series(good, total), LATENCY) if ep.action == "page"]


# ------------------------------------------------------------------ the incident

def security_events(rows: list[dict], attack: list[dict]) -> list[dict]:
    out, attack_fail = [], {}
    for a in attack:
        t = parse(a["minute"])
        n_f, n_s = int(a["failures"]), int(a["successes"])
        attack_fail[a["minute"]] = attack_fail.get(a["minute"], 0) + n_f
        for i in range(n_f + n_s):
            at = t + timedelta(seconds=60 * (i + 0.5) / (n_f + n_s))
            out.append({"at": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "event": "auth.failure" if i < n_f else
                        "auth.success", "network": a["network"], "credential": f"{a['network']}|{a['minute']}|{i}"})
    for r in rows:  # customers mistyping passwords, each from their own network
        t = parse(r["minute"])
        for i in range(max(0, int(r["signin_fail"]) - attack_fail.get(r["minute"], 0))):
            out.append({"at": (t + timedelta(seconds=7 * i % 60)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "event": "auth.failure", "network": f"home-{r['minute']}-{i}", "credential": f"h{i}"})
    return sorted(out, key=lambda e: e["at"])


def incident() -> dict:
    d = DATA / "incident-2027-02-02"
    rows, attack = read_csv(d / "minutes.csv"), read_csv(d / "attack-networks.csv")
    events = load_json(d / "events.json")["events"]
    rules = detection.load_rules(CONFIG / "service-rules.json")
    base = load_json(d / "baseline.json")
    baseline = detection.Baseline({}, {tuple(k.split("|")): v for k, v in base["maxima"].items()})
    sec = detection.from_security_events(security_events(rows, attack))
    alerts = [from_detection(a) for a in detection.evaluate(sec, rules, baseline)]
    pages = latency_pages(rows)
    routing = load_json(CONFIG / "routing.json")
    pager = Pager(routing["receivers"], routing["grouping"]["minutes"])
    for a in sorted(alerts + pages, key=lambda a: (a.at, a.rule)):
        Router(routing).dispatch(a, pager)
    # The checker's own knowledge: the quiet half hour before the deploy train, and which component's share of
    # database time each candidate cause would raise (the deploy changed relay.notify only).
    mechanisms = {"event:deploy-2027-02-02": "share:db_notify", "metric:signin_fail": "share:db_signin"}
    store = Store(datetime(2027, 2, 2, tzinfo=UTC), rows, events, alerts + pages, baseline=("14:30", "15:00"),
                  mechanisms=mechanisms)
    attempts = sum(int(a["failures"] + a["successes"]) for a in attack)
    takeovers = sum(int(a["successes"]) for a in attack)
    first_attack = min(parse(a["minute"]) for a in attack)
    return {"store": store, "alerts": sorted(alerts, key=lambda a: (a.at, a.rule)), "pages": pages,
            "attempts": attempts, "takeovers": takeovers, "networks": len({a["network"] for a in attack}),
            "first_attack": first_attack, "last_attack": max(parse(a["minute"]) for a in attack), "events": events,
            "pager": pager}


def judge(assistant: dict, store: Store, as_of: datetime) -> list:
    view = store.view(as_of)
    return [check_hypothesis(h, view) for h in assistant["hypotheses"]]


# ------------------------------------------------------------------ the game day

def gameday() -> dict:
    d = DATA / "gameday-2027-02-18"
    rows, plan = read_csv(d / "minutes.csv"), load_json(d / "plan.json")
    trail = detection.trail_records((d / "trail.jsonl").read_text(encoding="utf-8").splitlines())
    assistant, actions = load_json(d / "assistant.json"), load_json(d / "actions.json")["actions"]
    people = load_json(DATA / "people.json")
    routing = load_json(CONFIG / "routing.json")
    rules = detection.load_rules(CONFIG / "rules.json")
    day = datetime(2027, 2, 18, tzinfo=UTC)
    start = day.replace(hour=14)
    entries: list[Entry] = []

    # Alerts: the latency SLO, the worker stall (AL-001) and failing passes (AL-003), and agent-detection-v1.
    alerts = [a for a in latency_pages(rows) if a.at >= start]
    last_ok, back = parse(plan["worker_last_pass_before"]), parse(plan["worker_first_pass_after"])
    t = start
    while t <= day.replace(hour=16):
        if last_ok < t < back and (t - last_ok).total_seconds() > 300:
            alerts.append(AlertRecord(f"AL-001:{t:%H%M}", "AL-001", t, "page", "reliability",
                                      f"no completed pass for {(t - last_ok).total_seconds():.0f} s",
                                      (f"metric:relay.worker.heartbeat_age@{t:%H:%M}",)))
            break
        t += timedelta(minutes=1)
    failed = [r for r in rows if r["worker_pass_failed"] and parse(r["minute"]) >= start]
    if failed:
        alerts.append(AlertRecord("AL-003", "AL-003", parse(failed[0]["minute"]), "ticket", "reliability",
                                  "escalation passes failing", ("metric:relay.escalation.failed.5m",)))
    events = detection.from_trail(trail)
    baseline = detection.build_baseline([e for e in events if e.at < start], rules)
    alerts += [from_detection(a) for a in detection.evaluate([e for e in events if e.at >= start], rules, baseline)]
    alerts.sort(key=lambda a: (a.at, a.rule))

    router, gate = Router(routing), Gate(people, deploys=[])
    pager = Pager(routing["receivers"], routing["grouping"]["minutes"])
    trips = []
    for a in alerts:
        entries.append(Entry(a.at, "alert", a.rule, a.summary))
        for done in router.dispatch(a, pager, lambda g, actor, why: trips.append((a.at, g, actor))):
            kind = "automation" if done.startswith("automation") else done.split(":")[0]
            entries.append(Entry(a.at, kind, "killswitch.trip" if kind == "automation" else a.rule, done))
    first_export = next(e for e in events if e.at >= start and e.action == "export.start")
    gd_events = [{"id": "export-first", "kind": "export", "at": first_export.at.strftime("%Y-%m-%dT%H:%M:%SZ")}]
    store = Store(day, rows, gd_events, alerts, baseline=("13:30", "14:00"),
                  mechanisms={"metric:db_ms_per_query": "share:db_of_request"})

    verdicts = {}
    for batch in (assistant, assistant["later"]):
        at = parse(batch["asked_at"])
        for v in judge(batch, store, at):
            verdicts[v.hypothesis] = v
            entries.append(Entry(at, "hypothesis", v.hypothesis, f"{v.status}: {v.reason}"))

    def verdicts_at(t: datetime) -> dict:
        """The citation check's verdicts on every hypothesis made by `t`, judged as of `t`."""
        out = {}
        for batch in (assistant, assistant["later"]):
            if parse(batch["asked_at"]) <= t:
                out.update({v.hypothesis: v.status for v in judge(batch, store, t)})
        return out

    steps = [(parse(p["at"]), "propose", p) for p in assistant["proposals"]] +             [(parse(x["at"]), x["do"], x) for x in actions]
    for at, do, x in sorted(steps, key=lambda s: s[0]):
        try:
            if do in ("propose", "request"):
                who = "incident-assistant" if do == "propose" else x["by"]
                proof = make_proof(people, who, parse(x.get("proof_at", x["at"])), purpose="request",
                                   action=x["action"], args_sha256=args_sha256(x["args"]))
                gate.request(x["action"], x["args"], proof, at, because=x.get("because"), verdicts=verdicts_at(at))
                entries.append(Entry(at, "request", x["action"], f"by {who}, because {x.get('because')}"))
            elif do == "ack":
                rec = next(p.alert for p in pager.pages if p.alert.rule == x["rule"] and p.sent_at <= at)
                pager.ack(rec.alert_id, x["by"], at)
                entries.append(Entry(at, "ack", x["rule"], x["by"]))
            elif do == "decide":
                req = gate.find(x["request"])
                rid = req.request_id if req else x["request"]
                proof = make_proof(people, x["by"], parse(x["proof_at"]), purpose="decide", request_id=rid,
                                   args_sha256=req.args_sha256 if req else "")
                req = gate.decide(rid, proof, x["approve"], at)
                entries.append(Entry(at, "approval" if x["approve"] else "denial", req.action,
                                     f"{x['by']}: {req.status}"))
            elif do == "done":
                req = gate.find(x["request"])
                if req and req.status == "approved":
                    req.status = "done"
                    entries.append(Entry(at, "action", req.action, x.get("note", "")))
        except Refused as exc:
            entries.append(Entry(at, "refusal", x.get("action", x.get("request", "")), exc.code))
    pager.advance(day.replace(hour=16))
    entries.sort(key=lambda e: (e.at, e.kind))
    return {"entries": entries, "measures": fault_measures(entries, plan), "verdicts": verdicts, "gate": gate,
            "pager": pager, "plan": plan, "trips": trips,
            "exports": [(e.at, e.outcome) for e in events if e.at >= start and e.action == "export.start"], "injected": [r["detail"].get("job_name") for r in trail
                                                                      if "NOTE TO" in str(r["detail"])]}
