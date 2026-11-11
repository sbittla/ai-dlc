"""The capstone kit's reports.

    python -m capstone.report tracks
    python -m capstone.report check data/packs/relay-b-4.31.0
    python -m capstone.report ceilings data/packs/relay-b-4.31.0
    python -m capstone.report fixtures
    python -m capstone.report score data/scores/kestrel-a.json
    python -m capstone.report defense data/defense/kestrel-statements.json --seed <seed> --commitment <sha256>
    python -m capstone.report redteam data/redteam/osprey-on-kestrel.json
    python -m capstone.report remains --as-of 2027-07-26 [--track B]

`check` exits 1 when the pack has a blocking finding, `redteam` when the log has one, `score` when the team fails.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import LAB, load_json
from . import defense, evidence, redteam, remains, rubric


def _path(p: str) -> Path:
    path = Path(p)
    return path if path.exists() or path.is_absolute() else LAB / p


def render_tracks() -> str:
    t = evidence.tracks()
    lines = [f"# Capstone tracks ({t['version']})", ""]
    for tid, spec in t["tracks"].items():
        req = [r for r in spec["requirements"] if not r.get("optional")]
        lines.append(f"- {tid} {spec['title']}: {len(req)} required kinds of evidence, "
                     f"{len(spec['dimensions'])} rubric dimensions ("
                     + ", ".join(f"{d['title']} {d['weight']}%" for d in spec["dimensions"]) + ")")
    return "\n".join(lines) + "\n"


def render_check(pack_dir: str) -> tuple[str, int]:
    res = evidence.check(_path(pack_dir))
    s = evidence.summary(res)
    p = res.pack
    labels = ", ".join(f"{k} {v}" for k, v in sorted(s["labels"].items()))
    lines = [f"# Evidence pack: {p['team']}, track {p['track']}, {p['system']} {p['release']}, as of {p['as_of']}",
             "",
             f"Items: {s['items']} ({labels})",
             f"Required kinds of evidence: {s['requirements']}: ok {s['ok']}, with blocking findings "
             f"{s['blocked']}, missing {s['missing']}",
             f"Acceptance criteria with usable evidence: {s['criteria_ok']} of {s['criteria']}",
             f"Findings: {s['blocking']} blocking, {s['warnings']} warnings"
             + (" (" + ", ".join(f"{k} {v}" for k, v in s["codes"].items()) + ")" if s["codes"] else ""),
             f"Complete: {'yes' if s['complete'] else 'no'}", ""]
    lines += [f"- {f.line()}" for f in res.findings]
    return "\n".join(lines) + "\n", 0 if res.complete else 1


def render_ceilings(pack_dir: str) -> str:
    res = evidence.check(_path(pack_dir))
    spec = evidence.tracks()["tracks"][res.pack["track"]]
    ceil = rubric.ceilings(res)
    lines = ["# The highest score each dimension's evidence allows", "",
             "| Dimension | Weight | Ceiling | Why |", "| --- | ---: | ---: | --- |"]
    best = 0.0
    for d in spec["dimensions"]:
        cap, why = ceil[d["id"]]
        best += d["weight"] * cap / 100
        lines.append(f"| {d['title']} | {d['weight']}% | {cap} | {'; '.join(why) or '-'} |")
    best = round(best, 1)
    lines += ["", f"Highest total the evidence allows: {best} ({rubric.level(best)})"]
    return "\n".join(lines) + "\n"


def render_fixtures() -> str:
    lines = ["# Fixture packs", "", "| Fixture | Track | Complete | Blocking codes |", "| --- | --- | --- | --- |"]
    for d in sorted((LAB / "data" / "fixtures").iterdir()):
        if not (d / "pack.json").exists():
            continue
        res = evidence.check(d)
        codes = Counter(f.code for f in res.blocking)
        lines.append(f"| {d.name} | {res.pack['track']} | {'yes' if res.complete else 'no'} | "
                     f"{', '.join(f'{k} x{v}' if v > 1 else k for k, v in sorted(codes.items())) or '-'} |")
    return "\n".join(lines) + "\n"


def render_score(scores_path: str) -> tuple[str, int]:
    scores = load_json(_path(scores_path))
    res = evidence.check(_path(scores["pack"]))
    out = rubric.score(scores, res)
    lines = [f"# Rubric: {scores['team']}, track {scores['track']}", "",
             "| Dimension | Weight | Panel | Cap | Counted | Why capped |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for r in out["rows"]:
        lines.append(f"| {r['id']} | {r['weight']}% | {r['raw']} | {r['cap']} | {r['final']} | "
                     f"{'; '.join(r['why']) or '-'} |")
    lines += ["", f"Total: {out['total']}; level: {out['level']}; outcome: {out['outcome']}",
              "Gates: " + ", ".join(f"{g} {out['gates'].get(g, 'missing')}" for g in rubric.GATES)]
    lines += [f"- {n}" for n in out["notes"]]
    lines += ["", "| Member | Result | Why |", "| --- | --- | --- |"]
    lines += [f"| {m} | {lv} | {why or '-'} |" for m, lv, why in out["people"]]
    return "\n".join(lines) + "\n", 0 if out["level"] != "Fail" else 1


def render_defense(path: str, seed: str, commitment: str) -> str:
    st = load_json(_path(path))
    draws = defense.draw(st, seed, commitment)
    crit = defense.draw_criteria(st.get("criteria", []), seed, st["frozen_sha256"])
    lines = [f"# Defense draw for {st['team']} (seed {seed!r}, statements {st['frozen_sha256'][:12]})", ""]
    for d in draws:
        lines.append(f"## {d['member']}: {d['part']} {d['title']} (written by {', '.join(d['authors'])}"
                     f"{'; agent-assisted' if d['ai_assisted'] else ''}{'; solo draw' if d['solo'] else ''})")
        lines += [f"{n}. {q}" for n, q in enumerate(d["questions"], 1)]
        lines.append("")
    if crit:
        lines.append("Evidence walk-through: " + ", ".join(crit))
    return "\n".join(lines) + "\n"


def render_redteam(path: str) -> tuple[str, int]:
    log = load_json(_path(path))
    r = redteam.validate(log)
    lines = [f"# Red-team exchange: {log['attacker']} on {log['defender']}", "",
             f"Findings logged: {len(log.get('findings', []))}; valid: {len(r['valid'])}; "
             f"open critical or high: {len(r['open_high'])}",
             f"Credit: attacking team {r['attacker_credit']}, defending team {r['defender_credit']}", ""]
    lines += [f"- {f.line()}" for f in r["findings"]]
    return "\n".join(lines) + "\n", 0 if not r["findings"] else 1


def render_remains(as_of: str, track: str | None) -> str:
    v = remains.view(as_of, track)
    order = ("date passed, no completion recorded", "due later", "no date recorded")
    lines = [f"# What remains, as of {as_of}{' (track ' + track + ')' if track else ''}", "",
             f"Open items: {len(v['rows'])}; " + "; ".join(f"{k} {v['by_status'].get(k, 0)}" for k in order)
             + f"; no owner recorded {v['no_owner']}",
             "By capstone track: " + ", ".join(f"{t} {n}" for t, n in v["by_track"].items()), "",
             "| Chapter | Item | Owner | Date | Status | Tracks |", "| ---: | --- | --- | --- | --- | --- |"]
    for r in sorted(v["rows"], key=lambda r: (order.index(r["status"]), r.get("due") or "", r["chapter"])):
        lines.append(f"| {r['chapter']} | {r['what']} | {r.get('owner') or '-'} | "
                     f"{r.get('due') or r.get('due_condition') or '-'} | {r['status']} | {''.join(r['tracks'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m capstone.report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tracks")
    sub.add_parser("fixtures")
    for name in ("check", "ceilings"):
        sub.add_parser(name).add_argument("pack")
    sub.add_parser("score").add_argument("scores")
    d = sub.add_parser("defense")
    d.add_argument("statements")
    d.add_argument("--seed", required=True)
    d.add_argument("--commitment", required=True)
    sub.add_parser("redteam").add_argument("log")
    r = sub.add_parser("remains")
    r.add_argument("--as-of", required=True)
    r.add_argument("--track", choices=list("ABCD"))
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    code = 0
    if args.cmd == "tracks":
        text = render_tracks()
    elif args.cmd == "fixtures":
        text = render_fixtures()
    elif args.cmd == "check":
        text, code = render_check(args.pack)
    elif args.cmd == "ceilings":
        text = render_ceilings(args.pack)
    elif args.cmd == "score":
        text, code = render_score(args.scores)
    elif args.cmd == "defense":
        text = render_defense(args.statements, args.seed, args.commitment)
    elif args.cmd == "redteam":
        text, code = render_redteam(args.log)
    else:
        text = render_remains(args.as_of, args.track)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
