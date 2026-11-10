"""Lab 15.2's reports (provided). Run from starter/ or solution/:

    python -m canary.report rollouts          # R1-R6 under relay-canary-v1, and the all-at-once comparison
    python -m canary.report rollout --id R2   # one scenario's events
    python -m canary.report feature           # A1: the AI feature watched, the kill switch tripped
    python -m canary.report null              # A0: false trips over 40 re-seeded null runs
"""

from __future__ import annotations

import argparse
import sys

from . import DATA, load_json, policy, slos
from .killswitch import false_trips, watch
from .rollout import run_all_at_once, run_canary


def scenario(kind: str, sid: str) -> dict:
    return load_json(DATA / kind / f"{sid}.json")


def traffic_ids() -> list[str]:
    return load_json(DATA / "manifest.json")["traffic"]


def rollout_rows():
    pol, s = policy(), slos()
    return [(sid, scenario("traffic", sid), run_canary(scenario("traffic", sid), pol, s),
             run_all_at_once(scenario("traffic", sid), pol, s)) for sid in traffic_ids()]


def report_rollouts() -> str:
    lines = ["# Canary rollouts under relay-canary-v1 (simulated)", "",
             "| Scenario | What happens | Canary decision | Minute | Share | Canary requests | Bad answers from "
             "the canary | Pages | All at once |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    exposure = []
    for sid, scn, r, a in rollout_rows():
        lines.append(f"| {sid} | {scn['title']} | {r.decision} | {r.minute} | {r.percent}% | {r.canary.requests:,} | "
                     f"{r.bad_served:,} | {len(r.pages)} | {a.decision} |")
        if r.decision == "rolled back":
            exposure.append(f"| {sid} | {r.minute + 1} | {r.bad_served:,} | {a.minute} | {a.bad_served:,} |")
    lines += ["", "Until the bad version stopped serving (all at once: the same rule detects it and a person rolls "
              "back in the assumed 15 minutes):", "",
              "| Scenario | Canary: minutes | Canary: bad answers | All at once: minutes | All at once: bad answers |",
              "| --- | ---: | ---: | ---: | ---: |"] + exposure
    return "\n".join(lines) + "\n"


def report_rollout(sid: str) -> str:
    scn = scenario("traffic", sid)
    r = run_canary(scn, policy(), slos())
    lines = [f"# {sid}: {scn['title']}", ""] + [f"- minute {m}: {e}" for m, e in r.events]
    lines.append(f"\nDecision: {r.decision} at minute {r.minute}, {r.percent}% of traffic; canary served "
                 f"{r.canary.requests:,} requests, {r.canary.errors:,} errors and {r.canary.slow:,} slow answers")
    return "\n".join(lines) + "\n"


def report_feature() -> str:
    scn = scenario("ai", "A1")
    w = watch(scn, policy()["ai_feature_rule"])
    hours = (w.tripped_at or scn["hours"] * 60) / 60
    lines = [f"# A1: {scn['title']} (simulated)", "",
             f"Tripped at minute {w.tripped_at} ({hours:.2f} h after the rollout): cohort worse by {w.drop:.1f} "
             f"points, z = {w.z:.2f}",
             f"Suggestions served with the feature before the trip: {w.with_feature}; overridden: "
             f"{w.bad_with_feature}; overridden only because of the feature: {w.extra_bad}",
             f"First ticket from a rollout workspace after the trip, served on the stable route: minute "
             f"{w.first_after_trip}",
             f"Extra overridden suggestions per hour while the feature was on: {w.extra_bad / hours:.1f}", "",
             "Kill-switch log:"]
    lines += [f"- {r['at']} {r['action']} {r['feature']} by {r['actor']}: {r['outcome']} ({r['detail']})"
              for r in w.log]
    return "\n".join(lines) + "\n"


def report_null() -> str:
    scn = scenario("ai", "A0")
    trips = false_trips(scn, policy()["ai_feature_rule"])
    return (f"# A0: {scn['title']} (simulated)\n\nFalse trips: {len(trips)} of {scn['reseeds']} re-seeded runs "
            f"({', '.join(map(str, trips)) or 'none'}), checking every {scn['check_every_minutes']} minutes for "
            f"{scn['hours']} hours\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lab 15.2 reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rollouts")
    one = sub.add_parser("rollout")
    one.add_argument("--id", required=True)
    sub.add_parser("feature")
    sub.add_parser("null")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # tables use — and ×; Windows consoles default to cp1252
    text = {"rollouts": report_rollouts, "feature": report_feature, "null": report_null}.get(args.cmd)
    sys.stdout.write(text() if text else report_rollout(args.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
