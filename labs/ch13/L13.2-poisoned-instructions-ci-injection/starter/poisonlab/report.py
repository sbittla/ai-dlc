"""Lab 13.2 reports (provided). Run from starter/ or solution/:

    python -m poisonlab.report instructions     the check on 40 instruction-file changes
    python -m poisonlab.report reveal IC01      one change: what a reviewer sees, and what the model reads
    python -m poisonlab.report workflows        lint findings for both workflows
    python -m poisonlab.report ci               12 attack cases against both workflows, and with one control removed
    python -m poisonlab.report all
"""

from __future__ import annotations

import copy
import math
import sys

from . import DATA, load_json
from .ciagent import config_from_workflow, outcome
from .hidden import find_hidden, rendered, reveal_tags
from .instructions import check_change
from .workflows import lint


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} (95% interval {100 * lo:.1f}-{100 * hi:.1f}%)"


def changes() -> list[dict]:
    return load_json(DATA / "instructions" / "changes.json")["changes"]


def render_instructions() -> str:
    rows, tech = [], {}
    pois = ben = caught = alarms = 0
    for c in changes():
        rules = sorted({f.rule for f in check_change(c["path"], c["before"], c["after"])})
        t = c["truth"]
        if t["poisoned"]:
            pois += 1
            caught += bool(rules)
            s = tech.setdefault(t["technique"], [0, 0])
            s[0] += 1
            s[1] += bool(rules)
        else:
            ben += 1
            alarms += bool(rules)
        rows.append(f"| {c['id']} | {c['path']} | {'poisoned' if t['poisoned'] else 'benign'} | {t['technique']} | "
                    f"{', '.join(rules) or '-'} |")
    out = ["| Technique | Poisoned changes | Flagged |", "| --- | ---: | ---: |"]
    out += [f"| {k} | {n} | {f} |" for k, (n, f) in tech.items()]
    paths = sorted({c["path"] for c in changes()})
    out += ["", f"Changes: {pois + ben} ({pois} poisoned, {ben} benign) to {len(paths)} instruction files: "
            + ", ".join(paths) + ".",
            f"Poisoned changes flagged: {pct(caught, pois)}.",
            f"Benign changes flagged (false alarms): {pct(alarms, ben)}.",
            "Missed: the plain-language changes, which only a code owner reading for meaning can judge.", "",
            "| Change | File | Truth | Technique | Findings |", "| --- | --- | --- | --- | --- |"] + rows
    return "\n".join(out)


def render_reveal(cid: str) -> str:
    c = next(x for x in changes() if x["id"] == cid)
    added = [ln for ln in c["after"].splitlines() if ln not in set(c["before"].splitlines())]
    out = [f"# {cid} ({c['path']})", "", "Rendered (what a reviewer sees):"]
    out += [f"  + {rendered(ln)}" for ln in added]
    out += ["", "Raw, with smuggled tag text decoded (what the model reads):"]
    out += [f"  + {reveal_tags(ln)}" for ln in added]
    hidden = [h for ln in added for h in find_hidden(ln)]
    kinds = sorted({h.kind for h in hidden})
    out += ["", f"Hidden characters in the added lines: {len(hidden)} ({', '.join(kinds) or 'none'})."]
    return "\n".join(out)


def workflow(v: str) -> str:
    return (DATA / "workflows" / f"agent-on-comment.{v}.yml").read_text(encoding="utf-8")


def render_workflows() -> str:
    out = []
    for v in ("v1", "v2"):
        found = lint(workflow(v))
        out.append(f"{v}: {len(found)} finding(s)")
        out += [f"  {f.rule} line {f.line}: {f.message}" for f in found]
    return "\n".join(out)


def render_ci() -> str:
    cases = load_json(DATA / "ci-attacks" / "cases.json")["cases"]
    cfg = {v: config_from_workflow(workflow(v)) for v in ("v1", "v2")}
    out = ["| Case | Author | Technique | Goal | v1 | v2 (why it fails or succeeds) |",
           "| --- | --- | --- | --- | --- | --- |"]
    wins = {"v1": 0, "v2": 0}
    for c in cases:
        r = {v: outcome(c, cfg[v]) for v in cfg}
        for v in r:
            wins[v] += r[v][0]
        out.append(f"| {c['id']} | {c['author']} | {c['technique']} | {c['goal']} | "
                   f"{'succeeds' if r['v1'][0] else 'fails'} | {'succeeds' if r['v2'][0] else 'fails'}: {r['v2'][1]} |")
    n = len(cases)
    out += ["", f"Attacks that succeed against v1: {pct(wins['v1'], n)}.",
            f"Attacks that succeed against v2: {pct(wins['v2'], n)}.",
            f"Cases: {n} ({sum(c['author'] == 'outsider' for c in cases)} from an outsider's comment, "
            f"{sum(c['author'] == 'customer-text' for c in cases)} from customer ticket text a member asks about). "
            "A small set: read these as counts, not rates.", "",
            "v2 with one control removed (attacks that succeed):"]
    v1 = cfg["v1"]
    for label, change in (("no author gate", {"author_gate": None}), ("hidden text not stripped", {"strip_hidden": False}),
                          ("no link filter", {"link_filter": False}), ("v1's tools", {"tools": set(v1.tools)}),
                          ("comment text pasted into a run script", {"shell_interpolation": True}),
                          ("v1's permissions and secret", {"perms": dict(v1.perms), "secrets_in_env": True})):
        alt = copy.deepcopy(cfg["v2"])
        for k, val in change.items():
            setattr(alt, k, val)
        out.append(f"- {label}: {sum(outcome(c, alt)[0] for c in cases)}")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "all"
    renders = {"instructions": render_instructions, "workflows": render_workflows, "ci": render_ci}
    if cmd == "reveal":
        sys.stdout.write(render_reveal(argv[1]) + "\n")
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
