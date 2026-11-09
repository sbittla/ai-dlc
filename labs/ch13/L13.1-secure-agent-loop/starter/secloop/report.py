"""Lab 13.1 reports (provided). Run from starter/ or solution/:

    python -m secloop.report incident     the composite incident, replayed against 4.25.0's dependency gate
    python -m secloop.report gate AC017   one change, both stages
    python -m secloop.report catch        catch rates by category, stage and scanner, with Wilson intervals
    python -m secloop.report alarms       false alarms on clean changes and what the suppressions did
    python -m secloop.report fixes        re-verification of the agent's fix attempts
    python -m secloop.report release      the six release candidates
    python -m secloop.report all          everything above except gate

Every number is computed from data/, which is generated and simulated (see the README).
"""

from __future__ import annotations

import sys
from datetime import datetime

from . import DATA, load_json, mirror_policy
from .catch import catch_report, wilson
from .deps import check_requirements
from .loop import fix_summary, run
from .release import check_release


ORDER = ["sql-injection", "broken-authorization", "hardcoded-secret", "weak-crypto", "unsafe-deserialization",
         "command-injection", "path-traversal", "vulnerable-dependency", "hallucinated-package", "typosquat",
         "dependency-confusion", "iac-misconfiguration"]


def pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / n:.0f}%; 95% interval {100 * lo:.1f}-{100 * hi:.1f}%)"


def dur(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = [f"{d} d"] * bool(d) + [f"{h} h"] * bool(h) + [f"{m} min"] * bool(m) + [f"{s} s"] * bool(s)
    return " ".join(parts) or "0 s"


def render_incident() -> str:
    inc = load_json(DATA / "incident" / "timeline.json")
    ev = [(datetime.fromisoformat(e["at"].replace("Z", "+00:00")), e["what"]) for e in inc["events"]]
    first = next(x for x, w in ev if w.startswith("jwt-oidc-verify 1.0.0"))
    install = next(x for x, w in ev if "runs pip install" in w)
    exfil = next(x for x, w in ev if "posts the session" in w)
    app_issued = next(x for x, w in ev if "installation token issued" in w)
    app_exp = next(x for x, w in ev if w.startswith("stolen App token expires"))
    found = next(x for x, w in ev if w.startswith("sam.o, reviewing"))
    relay_exp = next(x for x, w in ev if w.startswith("stolen Relay agent token expires"))
    pr = next(x for x, w in ev if "opens draft PR" in w)
    lines = ["# The hallucinated package (composite; generated timeline)", ""]
    lines += [f"- {x:%a %Y-%m-%d %H:%M:%S} UTC  {w}" for x, w in ev]
    lines += ["",
              f"Package age at install: {(install - first).days} days.",
              f"Install to exfiltration: {dur((exfil - install).total_seconds())}.",
              f"Stolen App token usable for {dur((app_exp - exfil).total_seconds())} "
              f"(issued {app_issued:%H:%M:%S}, one hour).",
              f"Stolen Relay agent token: {dur((relay_exp - exfil).total_seconds())} left, never used.",
              f"Install to the agent's pull request: {dur((pr - install).total_seconds())}.",
              f"Install to discovery: {dur((found - install).total_seconds())}.", ""]
    ch = inc["change"]
    pub = load_json(DATA / "packages" / "public-index.json")
    found_dep = check_requirements(ch["id"], ch["requirements"]["file"], ch["requirements"]["added_lines"],
                                   mirror_policy(), load_json(DATA / "packages" / "mirror-index.json"), pub)
    lines.append("4.25.0's dependency gate on the agent's change:")
    lines += [f"- {f.rule}: {f.message}" for f in found_dep]
    return "\n".join(lines)


def render_gate(cid: str) -> str:
    out = run()[cid]
    lines = [f"# {cid}"]
    for stage in ("pre-commit", "ci"):
        r = out["results"][stage]
        lines.append(f"{stage}: exit {r.status}")
        lines += [f"  block  {f.scanner} {f.rule} {f.path}:{f.line} ({f.severity:.1f})" for f in r.blocking]
        lines += [f"  warn   {f.scanner} {f.rule} {f.path}:{f.line} ({f.severity:.1f})" for f in r.warnings]
        lines += [f"  suppressed {f.rule} by {s}" for f, s in r.suppressed]
        lines += [f"  ignored suppression {s}: {why}" for s, why in r.ignored_suppressions]
    return "\n".join(lines)


def render_catch() -> str:
    truth = load_json(DATA / "changes" / "truth.json")["changes"]
    outcomes = run()
    rep = catch_report(outcomes, truth)
    no_dep = sum(1 for c, o in outcomes.items() if truth[c]["seeded"] and o["blocking_scanners"] - {"depgate"})
    dep_only = [c for c, o in outcomes.items() if truth[c]["seeded"] and o["blocking_scanners"] == {"depgate"}]
    lines = ["| Seeded weakness | Changes | Blocked before commit | Blocked in CI only | Escaped |",
             "| --- | ---: | ---: | ---: | ---: |"]
    rows = sorted(rep.rows, key=lambda r: ORDER.index(r.name))
    for r in rows + [rep.total]:
        lines.append(f"| {r.name} | {r.n} | {r.pre_commit} | {r.ci_only} | {r.escaped} |")
    t = rep.total
    lines += ["", f"Caught at either stage: {pct(t.caught, t.n)}.",
              f"Caught before commit: {pct(t.pre_commit, t.n)}.",
              "Each scanner alone (seeded changes it blocks): "
              + ", ".join(f"{s} {n}" for s, n in rep.by_scanner.items()) + ".",
              f"Without the dependency gate (scanners only): {pct(no_dep, rep.total.n)}; "
              f"{len(dep_only)} seeded changes are caught by the dependency gate alone.",
              f"Clean changes blocked: {rep.clean_blocked} of {rep.clean_n}.",
              "Small categories: an interval on 4 to 12 changes is wide; read them as counts."]
    return "\n".join(lines)


def render_alarms() -> str:
    truth = load_json(DATA / "changes" / "truth.json")["changes"]
    with_sups, without = run(), run(suppressions=[])
    clean = [c for c in sorted(truth) if not truth[c]["seeded"]]
    flagged = [c for c in clean if with_sups[c]["results"]["ci"].blocking or with_sups[c]["results"]["ci"].warnings
               or with_sups[c]["results"]["ci"].suppressed]
    b0 = sum(without[c]["ci"] == 1 for c in clean)
    b1 = sum(with_sups[c]["ci"] == 1 for c in clean)
    warn = sum(bool(with_sups[c]["results"]["ci"].warnings) for c in clean)
    lines = [f"Clean changes with any finding: {len(flagged)} of {len(clean)}.",
             f"Blocked without suppressions: {b0}; with the reviewed suppressions: {b1}; warnings only: {warn}.",
             "", "| Clean change | What it is | Finding | Severity | Outcome |", "| --- | --- | --- | --- | --- |"]
    for c in flagged:
        r = with_sups[c]["results"]["ci"]
        f = (r.blocking + r.warnings + [x for x, _ in r.suppressed])[0]
        outcome = "suppressed" if r.suppressed else ("blocked" if r.blocking else "warning")
        lines.append(f"| {c} | {truth[c]['variant']} | {f.scanner} {f.rule} | {f.severity:.1f} | {outcome} |")
    sups = load_json(DATA / "suppressions.json")["suppressions"]
    lines += ["", f"Suppressions proposed: {len(sups)}; proposed by the agent: "
              f"{sum(s['author'] == 'coding-session' for s in sups)}; reviewed by the agent: "
              f"{sum(s['reviewed_by'] == 'coding-session' for s in sups)}.", "",
              "| Suppression | Change | Proposed by | Reviewed by | Applied | Why not |",
              "| --- | --- | --- | --- | --- | --- |"]
    for s in sups:
        r = with_sups[s["for_change"]]["results"]["ci"]
        applied = any(sid == s["id"] for _, sid in r.suppressed)
        why = next((w for sid, w in r.ignored_suppressions if sid == s["id"]), "")
        kind = "seeded weakness" if truth[s["for_change"]]["seeded"] else truth[s["for_change"]]["variant"]
        lines.append(f"| {s['id']} | {s['for_change']} ({kind}) | {s['author']} | {s['reviewed_by']} | "
                     f"{'yes' if applied else 'no'} | {why} |")
    return "\n".join(lines)


def render_fixes() -> str:
    s = fix_summary()
    lines = [f"Fix attempts: {s['attempts']}, every one claimed as fixed.", "",
             "| Re-verification | Accepted | Bad fixes accepted |", "| --- | ---: | ---: |"]
    for mode, (acc, bad) in s["modes"].items():
        lines.append(f"| {mode} | {acc} | {bad} |")
    lines += ["", "Kinds: " + ", ".join(f"{k} {n}" for k, n in sorted(s["kinds"].items())) + ".",
              "Refusal reasons: " + ", ".join(f"{k} {n}" for k, n in s["reasons"].items()) + "."]
    return "\n".join(lines)


def render_release() -> str:
    trust = load_json(DATA / "releases" / "trust-root.json")
    lines = ["| Candidate | Findings | Verdict |", "| --- | --- | --- |"]
    for rc in ("RC-1", "RC-2", "RC-3", "RC-4", "RC-5", "RC-6"):
        found = check_release(DATA / "releases" / rc, trust, "4.25.0")
        lines.append(f"| {rc} | {', '.join(r for r, _ in found) or 'none'} | {'deploy' if not found else 'refuse'} |")
    lines.append("")
    for rc in ("RC-2", "RC-3", "RC-4", "RC-5", "RC-6"):
        for rule, msg in check_release(DATA / "releases" / rc, trust, "4.25.0"):
            lines.append(f"- {rc} {rule}: {msg}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "all"
    renders = {"incident": render_incident, "catch": render_catch, "alarms": render_alarms,
               "fixes": render_fixes, "release": render_release}
    if cmd == "gate":
        sys.stdout.write(render_gate(argv[1]) + "\n")
    elif cmd == "all":
        for name, fn in renders.items():
            sys.stdout.write(f"\n## {name}\n\n{fn()}\n")
    elif cmd in renders:
        sys.stdout.write(renders[cmd]() + "\n")
    else:
        sys.stderr.write(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
