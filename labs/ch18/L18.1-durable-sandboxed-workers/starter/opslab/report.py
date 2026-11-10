"""Lab 18.1's reports (provided). Run from starter/ or solution/:

    python -m opslab.report incident    # the refund pilot replayed: refunds, duplicates, causes
    python -m opslab.report layers      # each combination of dedup, heartbeat and ledger, on the same deliveries
    python -m opslab.report escapes     # the escape attempts, the pilot's way and in Relay's sandbox
    python -m opslab.report drills      # fault injection on the helper as a queue worker
    python -m opslab.report trace       # one job traced end to end, and where its time went
    python -m opslab.report all
"""

from __future__ import annotations

import sys

from . import drills, escapes, replay, traces


def _money(n: int) -> str:
    return f"${n:,}"


def render_incident() -> str:
    tickets, deliveries = replay.load()
    s = replay.pilot_refunds(tickets, deliveries)
    long_n, total = replay.long_runs(deliveries)
    causes = ", ".join(f"{c.replace('_', ' ')} {n}" for c, n in s.by_cause.items())
    lines = [
        "Refund pilot, Monday 1 to Tuesday 9 March 2027 (simulated from data/pilot/; configured, not measured)",
        f"Billing tickets: {s.tickets}; real duplicate charges (eligible for a refund): {s.eligible}.",
        f"Queue deliveries: {s.deliveries} for {s.tickets} tickets.",
        f"Deliveries whose processing passed the 60 s visibility timeout: {long_n} of {total}.",
        f"Refunds issued: {s.refunds} for {s.eligible} eligible charges.",
        f"Duplicate refunds: {s.duplicate_refunds} on {s.charges_refunded_twice} charges, {_money(s.extra_usd)} "
        f"refunded twice.",
        f"Duplicate refunds by cause: {causes}.",
    ]
    return "\n".join(lines)


def render_layers() -> str:
    tickets, deliveries = replay.load()
    rows = ["| Layers on | Refunds | Duplicate refunds | Refunded twice | Left by |", "| --- | ---: | ---: | ---: | --- |"]
    for combo, s in replay.layer_table(tickets, deliveries):
        left = ", ".join(f"{c.replace('_', ' ')} {n}" for c, n in s.by_cause.items()) or "-"
        rows.append(f"| {' + '.join(combo) or 'none (the pilot)'} | {s.refunds} | {s.duplicate_refunds} | "
                    f"{_money(s.extra_usd)} | {left} |")
    return "\n".join(rows)


def render_escapes() -> str:
    rows = ["| ID | Attempt | Pilot's way | Relay's sandbox | Last refusal |", "| --- | --- | --- | --- | --- |"]
    results = escapes.run_all()
    for r in results:
        rows.append(f"| {r['id']} | {r['what']} | {r['pilot']} | {r['sandbox']} | {r['refusal']} |")
    attempts = [r for r in results if r["id"].startswith("E")]
    pilot_run = [r for r in attempts if r["pilot"] != "not run"]
    rows.append("")
    rows.append(f"Escape attempts: {len(attempts)}. Run the pilot's way: {len(pilot_run)}, of which reached what they "
                f"tried: {sum(r['pilot'] == 'reached' for r in pilot_run)}.")
    contained = sum(r["sandbox"] in ("refused", "stopped", "nothing") for r in attempts)
    rows.append(f"In the sandbox: refused {sum(r['sandbox'] == 'refused' for r in attempts)}, stopped by a limit "
                f"{sum(r['sandbox'] == 'stopped' for r in attempts)}, found nothing "
                f"{sum(r['sandbox'] == 'nothing' for r in attempts)}; contained {contained} of {len(attempts)}.")
    legit = [r for r in results if r["id"].startswith("L")]
    rows.append(f"Legitimate attempts that still work in the sandbox: {sum(r['sandbox'] == 'ok' for r in legit)} of "
                f"{len(legit)}.")
    return "\n".join(rows)


def render_drills() -> str:
    rows = ["| Drill | Fault | Job | Run | PRs | Worker outcomes | Verdict |", "| --- | --- | --- | --- | ---: | --- | --- |"]
    details = []
    passed = 0
    for drill, o, ok, mismatches in drills.run_all():
        passed += ok
        compact = []
        for out in o["outcomes"]:
            if compact and compact[-1][0] == out:
                compact[-1][1] += 1
            else:
                compact.append([out, 1])
        outs = ", ".join(f"{name} x{n}" if n > 1 else name for name, n in compact)
        job = o["job"] + (f" ({o['dead_reason']})" if o.get("dead_reason") else "")
        run = (o["run"] or "-") + (f" ({o['run_reason']})" if o.get("run_reason") else "")
        rows.append(f"| {drill['id']} | {drill['fault']} | {job} | {run} | {o['prs']} | {outs} | "
                    f"{'pass' if ok else 'FAIL: ' + '; '.join(mismatches)} |")
        if drill["id"] == "F1":
            details.append(f"F1: attempts {o['attempts']}; the ledger repeated the pull request call "
                           f"{o['ledger_attempts'] - 1} time, and the code host's key returned the existing one.")
        if drill["id"] == "F2":
            details.append(f"F2: second delivery created a new job: {o['duplicate_created']}; a second worker "
                           f"polling during the {o['run_tests_s']} s test step got: {', '.join(o['second_worker'])} "
                           f"(lease {o['lease_s']:.0f} s, extended between steps).")
        if drill["id"] == "F3":
            details.append("F3: retry delays " + ", ".join(f"{d:.1f} s" for d in o["retry_delays_s"])
                           + f"; attempts {o['attempts']}.")
        if drill["id"] == "F4":
            details.append(f"F4: calls refused with 429: {o['rate_limited_attempts']}; worker passes paused by the "
                           f"breaker: {o['outcomes'].count('paused')}; breaker: {' -> '.join(o['breaker_states'])}.")
        if drill["id"] == "F5":
            details.append("F5: sandbox refusals " + ", ".join(o["refused"]) + ".")
        if drill["id"] == "F6":
            details.append(f"F6: refused tool {o['refused_tool']} ({o['refusal_code']}), "
                           f"{o['trip_to_refusal_s']:.0f} simulated seconds after the trip.")
    rows.append("")
    rows.append(f"Drills passed: {passed} of {len(rows) - 3}.")
    return "\n".join(rows + details)


def render_trace() -> str:
    r = traces.traced_baseline()
    b = traces.breakdown(r["events"], r["spans"])
    return "\n".join([
        "Drill F0 traced (simulated clock: 2 s per model call, 100 s for the test step; approval after 600 s)",
        f"Attempts (process_job spans): {b['attempts']}, each linked to the request's span: "
        f"{'yes' if b['linked'] else 'no'}.",
        f"Tool calls traced: {b['tool_calls']}.",
        f"Queue wait {b['queue_wait']:.1f} s; agent working {b['agent']:.1f} s, of which the test step "
        f"{b['tests']:.1f} s; waiting for approval {b['approval_wait']:.1f} s; total {b['total']:.1f} s.",
    ])


RENDERERS = {"incident": render_incident, "layers": render_layers, "escapes": render_escapes,
             "drills": render_drills, "trace": render_trace}


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else "all"
    names = list(RENDERERS) if which == "all" else [which]
    for name in names:
        sys.stdout.write(RENDERERS[name]() + "\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
