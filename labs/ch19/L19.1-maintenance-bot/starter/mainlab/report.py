"""Provided: print every number Chapter 19 quotes from Lab 19.1.

    python -m mainlab.report incident|controls|worked|demo|replay|month|dst|all
"""

from __future__ import annotations

import sys

from . import demo, dst, incident, measure, worked
from .world import load


def render_incident() -> str:
    t = incident.timeline(load("incident-2027-05-20.json"))
    return "\n".join([
        "Thursday 20 May 2027 (composite; per-minute counts generated).",
        f"New version first served: {t.first_affected} UTC; to every user from {t.full_from}; sign-ins restored "
        f"{t.restored}.",
        f"Minutes with some users locked out: {t.affected_minutes}; with every user locked out: {t.full_minutes}.",
        f"Failed sign-in attempts while affected: {t.failures_affected:,} (baseline failure share before: "
        f"{t.baseline_failure_pct}%).",
        f"Accounts that tried to sign in during the full lockout: {t.accounts_during_full:,}.",
        f"From the SD-001 page to restored sign-ins: {t.page_to_restore_minutes} minutes."]
        + [_release(v) for v in ("2.4.1", "2.5.0")]
        + [f"{e['at']}  {e['what']}" for e in load("incident-2027-05-20.json")["events"]])


def _release(version: str) -> str:
    f = next(x for x in load("mirror.json")["projects"][0]["files"] if x["version"] == version)
    early = f" (released early by {f['released_early_by']})" if f.get("released_early_by") else ""
    return f"sessionkeel {version}: released {f['released_on']}, served from {_served(f)}{early}"


def _served(f: dict) -> str:
    import datetime as dt
    days = 0 if f.get("released_early_by") else load("mirror.json")["new_release_quarantine_days"]
    return (dt.date.fromisoformat(f["released_on"]) + dt.timedelta(days=days)).isoformat()


def render_controls() -> str:
    c = incident.controls(load("incident-2027-05-20.json"))
    p = c.plan
    return "\n".join([
        f"Plan on 2027-05-20: sessionkeel {p.current} -> {p.target} ({p.bump}); reviews: {', '.join(p.reviews)}.",
        f"App tests on {p.target}: {c.app_tests.result} ({c.app_tests.detail}).",
        f"Round trip on {p.target}: {c.round_trip.result} ({c.round_trip.detail}).",
        f"Pinned defaults on {p.target}: {c.defaults.result} ({c.defaults.detail}).",
        f"Guard on the 5% stage: tripped at {c.guard_minute} (canary failures {c.guard_canary_pct}%, stable "
        f"{c.guard_stable_pct}%); canary sign-ins refused before the trip: {c.canary_failures_before_trip}."])


def render_worked() -> str:
    w = worked.fix_vulnerability()
    lines = [_release("2.4.2"),
             f"Triage: {w.triage.report_id} -> {w.triage.task_type} ({w.triage.fields['advisory']}; locked "
             f"{w.triage.fields['locked']}, fixed {w.triage.fields['fixed']}; untrusted: {w.triage.untrusted}).",
             f"Plan: sessionkeel {w.plan.current} -> {w.plan.target} ({w.plan.bump}); reviews: "
             f"{', '.join(w.plan.reviews)}.",
             f"Reproduction: before {w.reproduction.before.result} ({w.reproduction.before.detail}); after "
             f"{w.reproduction.after.result} ({w.reproduction.after.detail}); outcome {w.reproduction.outcome}."]
    lines += w.bundle.table()
    lines += [f"Proposal {w.proposal.proposal_id}: {w.proposal.status}.",
              "Refused approvals: " + ", ".join(w.refusals) + ".",
              f"Approved by aisha.r: {w.decided.status}. Pull request #{w.pr['number']} opened "
              f"(replayed: {w.pr['replayed']}).",
              f"Audit records: {len(w.world.trail.records)}, of which refusals: {len(w.world.refused())}."]
    return "\n".join(lines)


def render_demo() -> str:
    r = demo.safe_rejection()
    i = demo.injection()
    b = demo.rollback()
    return "\n".join([
        "1. Safe rejection (sessionkeel 2.5.0 on 20 May, through the bot):",
        "   " + "; ".join(f"{c.name} {c.result}" for c in r.checks) + ".",
        f"   Proposal refused: {r.code}; audited: {r.audited}.",
        "2. Injection attempt blocked (ISS-2291, inert placeholder):",
        f"   Agent step: {i.status}; run tainted: {i.tainted}; refusals: {', '.join(i.refusals)}.",
        f"   Files changed: {', '.join(i.files_changed) or 'none'}. The desk, asked for the workflow path: "
        f"{i.desk_code}.",
        "3. Rollback (sessionkeel 2.4.3 on 29 June):",
        "   " + _release("2.4.3") + ".",
        f"   Plan: {b.plan.current} -> {b.plan.target} ({b.plan.bump}); guard tripped at canary minute "
        f"{b.trip_minute} (canary failures {b.canary_pct}%, stable {b.stable_pct}%, z {b.z}).",
        f"   Canary sign-ins refused before the trip: {b.canary_failures_before_trip}. Reverted to {b.reverted_to}; "
        f"lock matches the mirror: {b.lock_check}.",
        f"   Cause: on {b.plan.target} {b.cause.result} ({b.cause.detail}); on {b.plan.current} "
        f"{b.cause_before.result} ({b.cause_before.detail})."])


def render_replay() -> str:
    p = measure.paired(load("history.json"))
    return "\n".join([
        f"Updates replayed: {p.updates} (January to May 2027; regressions and what sees them are configured).",
        f"Regression reached all users: old rule {len(p.old_reached)} ({', '.join(p.old_reached)}); new policy "
        f"{len(p.new_reached)} ({', '.join(p.new_reached)}).",
        f"Discordant: old only {p.b}, new only {p.c}; exact McNemar p = {p.p:.3f}.",
        "Stopped by: " + ", ".join(f"{k} {v}" for k, v in p.stopped_by.items()) + ".",
        f"Merged with no person under the old rule: {p.old_auto_merged}; sent to @relay/security under the new "
        f"policy: {p.new_to_people}."])


def render_month() -> str:
    rows, verdicts = measure.month()
    out = ["A simulated month, 9 June to 9 July 2027: the runs the bot would have made (configured outcomes).",
           "| Task type | Tier | Runs | Success | Harm (regression or rollback, of merged) | Intervention | "
           "Violations | $/run | T4 criteria |", "| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- |"]
    for m in rows:
        tier, v = verdicts[m.task_type]
        harm = m.harm.text() if m.harm.n else "-"
        out.append(f"| {m.task_type} | {tier} | {m.runs} | {m.success.text()} | {harm} | {m.intervention.text()} | "
                   f"{m.violations} | {m.usd_per_run:.4f} | {v} |")
    total = sum(m.runs for m in rows)
    out.append(f"Runs: {total}; total cost ${sum(m.usd for m in rows):.2f}. A 5% upper bound at zero harms needs "
               f"{measure.clean_runs_for()} merged changes.")
    return "\n".join(out)


def render_dst() -> str:
    d = dst.extend_table()
    return "\n".join([
        f"Run {dst.RUN} ({dst.RUN_DATE}); rules {d.rules} reviewed by {d.reviewed_by} on {d.reviewed_on}.",
        f"Rules reproduce the reviewed table: {d.matching} of {d.total} transitions (2026-2027).",
        f"Transitions added for 2028: {d.new_transitions_2028}.",
        f"Approved tests that pin the old end ({len(d.pinned)}): {', '.join(d.pinned)}.",
        f"Proposal: {d.code}."])


SECTIONS = {"incident": render_incident, "controls": render_controls, "worked": render_worked, "demo": render_demo,
            "replay": render_replay, "month": render_month, "dst": render_dst}


def main(argv: list[str]) -> int:
    names = list(SECTIONS) if not argv or argv[0] == "all" else argv
    for n in names:
        print(f"## {n}\n{SECTIONS[n]()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
