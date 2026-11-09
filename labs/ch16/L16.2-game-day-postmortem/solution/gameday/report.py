"""Lab 16.2's reports (provided). Every number Chapter 16 quotes from this lab is printed here.

    python -m gameday.report incident      # the 2 February incident, replayed with 4.27.0's detection
    python -m gameday.report hypotheses    # the assistant's hypotheses, checked as of 15:18 and 15:41
    python -m gameday.report gameday       # the 18 February game day: timeline, measures, gate audit
    python -m gameday.report postmortem    # the agent's draft and the team's postmortem, checked
"""

from __future__ import annotations

import sys
from datetime import timedelta

from . import DATA
from .postmortem import check
from .replay import gameday, incident, judge
from .store import load_json, parse


def out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def mins(a, b) -> str:
    s = int((b - a).total_seconds())
    return f"{s // 60} min" if s % 60 == 0 else f"{s // 60} min {s % 60} s"


def incident_report() -> dict:
    r = incident()
    ev = {e["id"]: e for e in r["events"]}
    page = r["pages"][0]
    rollback_done, mitigation = parse(ev["rollback-2027-02-02"]["done"]), parse(ev["mitigation"]["at"])
    declared = parse(ev["security-p1"]["at"])
    out(f"Attack (generated): {r['attempts']:,} sign-in attempts from {r['networks']} networks, "
        f"{r['first_attack']:%H:%M} to {r['last_attack']:%H:%M}; {r['takeovers']} succeeded")
    out(f"Latency SLO page: {page.at:%H:%M} ({mins(r['first_attack'], page.at)} after the first attack request)")
    out(f"Rollback done {rollback_done:%H:%M} ({mins(page.at, rollback_done)} after the page); attack continued "
        f"{mins(rollback_done, mitigation)} until the mitigation at {mitigation:%H:%M}")
    out(f"Security P1 declared {declared:%H:%M}: {mins(r['first_attack'], declared)} after the first attack request")
    v0 = load_json(DATA / "incident-2027-02-02" / "assistant-v0.json")
    out(f"Assistant v0 asked {parse(v0['asked_at']):%H:%M}: {v0['answer']}")
    out("Events: " + "; ".join(f"{e['id']} {parse(e['at']):%H:%M}" + (f"-{parse(e['done']):%H:%M}" if "done" in e else "")
                               for e in r["events"]))
    out("Replayed with relay-service-detection-v1 (as 4.27.0 deploys it):")
    firsts = {}
    for a in r["alerts"]:
        firsts.setdefault(a.rule, a)
    for rule, a in sorted(firsts.items()):
        out(f"  {rule} first at {a.at:%H:%M} ({mins(r['first_attack'], a.at)} after the first attack request): "
            f"{a.summary}")
    counts = ", ".join(f"{k} {sum(1 for a in r['alerts'] if a.rule == k)}" for k in sorted(firsts))
    pages = [p for p in r["pager"].pages if p.alert.rule.startswith("SD-")]
    out(f"  alerts in all: {len(r['alerts'])} ({counts}); pages after grouping by rule for an hour: {len(pages)}")
    return r


def hypotheses_report() -> dict:
    r = incident()
    d = DATA / "incident-2027-02-02"
    res = {}
    st = r["store"]
    out(f"Share of database time, 15:08-15:16: sign-in writes {st.mean('share:db_signin', '15:08', '15:16'):.1%}, "
        f"the deploy's component (notifications) {st.mean('share:db_notify', '15:08', '15:16'):.1%}")
    for name in ("assistant-v0", "assistant-v1"):
        a = load_json(d / f"{name}.json")
        for when in ("15:18", "15:41"):
            as_of = parse(f"2027-02-02T{when}:00Z")
            for v in judge(a, r["store"], as_of):
                out(f"{a['version']} {v.hypothesis} as of {when}: {v.status}"
                    f"{' (' + v.reason + ')' if v.reason else ''}; citations {', '.join(v.results)}")
                res[(name, v.hypothesis, when)] = v.status
    # The 15:22 rollback request, as ADR-039's gate would have received it from the assistant.
    from .remediate import Gate, Refused, args_sha256, make_proof
    v0 = load_json(d / "assistant-v0.json")
    people = load_json(DATA / "people.json")
    at = parse("2027-02-02T15:22:00Z")
    proposal = v0["proposals"][0]
    verdicts = {v.hypothesis: v.status for v in judge(v0, r["store"], at)}
    gate = Gate(people, deploys=[parse("2027-02-02T15:00:00Z")], store=r["store"],
                hypotheses={h["id"]: h for h in v0["hypotheses"]})
    proof = make_proof(people, "incident-assistant", at, purpose="request", action=proposal["action"],
                       args_sha256=args_sha256(proposal["args"]))
    try:
        gate.request(proposal["action"], proposal["args"], proof, at, because=proposal["because"])
        outcome = "requested"
    except Refused as exc:
        outcome = f"refused ({exc.code})"
    out(f"Gate at 15:22: the assistant's {proposal['action']} because {proposal['because']} "
        f"({verdicts[proposal['because']]}): {outcome}")
    res["gate_1522"] = outcome
    v1 = load_json(d / "assistant-v1.json")
    gate1 = Gate(people, deploys=[parse("2027-02-02T15:00:00Z")], store=r["store"],
                 hypotheses={h["id"]: h for h in v1["hypotheses"]})
    for hid in ("H1", "H2", "H3"):  # the same rollback, citing each of v1's hypotheses in turn
        proof = make_proof(people, "incident-assistant", at, purpose="request", action=proposal["action"],
                           args_sha256=args_sha256(proposal["args"]), because=hid)
        try:
            gate1.request(proposal["action"], proposal["args"], proof, at, because=hid)
            outcome = "requested"
        except Refused as exc:
            outcome = f"refused ({exc.code})"
        out(f"Gate at 15:22: the same rollback because v1's {hid} ({gate1.verdict(hid, at)[1]}): {outcome}")
        res[f"gate_1522_{hid}"] = outcome
    return res


def gameday_report() -> dict:
    g = gameday()
    out("Game day, Thursday 18 February 2027 (simulated; faults configured in data/gameday-2027-02-18/plan.json)")
    for e in g["entries"]:
        out(f"  {e.at:%H:%M:%S} {e.kind:<10} {e.what:<18} {e.detail}")
    out("Measures per fault:")
    for f, m in g["measures"].items():
        out(f"  {f}: first alert {m['first_alert']} after {m['detect_min']} min; first page {m['first_page']}, "
            f"acknowledged {m['ack_min']} min later; mitigated {m['mitigate_min']} min after the fault began")
    esc = [(p.alert.rule, to, at) for p in g["pager"].pages for at, to in p.escalations]
    out("Pages escalated: " + (", ".join(f"{r} to {to} at {at:%H:%M}" for r, to, at in esc) or "none"))
    refused = [a for a in g["gate"].audit if a["outcome"] == "refused"]
    out(f"Gate audit: {len(g['gate'].audit)} records, {len(refused)} refusals:")
    for a in g["gate"].audit:
        out(f"  {a['at']} {a['outcome']:<9} {a['action']:<18} by {a['by']}{' (' + a['code'] + ')' if a['code'] else ''}")
    out(f"Untrusted text found in telemetry: {g['injected'][0]!r}")
    out("Exports by gameday-red after 14:00: " + ", ".join(f"{t:%H:%M:%S} {o}" for t, o in g["exports"]))
    return g


def postmortem_report() -> dict:
    people = sorted(load_json(DATA / "people.json")["people"])
    res = {}
    for name in ("draft-agent", "reference"):
        found = check((DATA / "postmortems" / f"{name}.md").read_text(encoding="utf-8"), people)
        codes = {}
        for code, _ in found:
            codes[code] = codes.get(code, 0) + 1
        out(f"{name}.md: {len(found)} finding(s) {dict(sorted(codes.items()))}")
        for code, detail in found:
            out(f"  {code} {detail}")
        res[name] = found
    return res


COMMANDS = {"incident": incident_report, "hypotheses": hypotheses_report, "gameday": gameday_report,
            "postmortem": postmortem_report}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        out(__doc__)
        return 2
    COMMANDS[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
