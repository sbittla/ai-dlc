"""Command-line reports for Lab 14.2 (provided). Run from starter/ or solution/:

    python -m govpack.report matrix [--draft]
    python -m govpack.report dpia [--draft]
    python -m govpack.report licenses
    python -m govpack.report aiact
    python -m govpack.report claims [--draft]
    python -m govpack.report pack > ../evidence/governance-pack.md

Every number the chapter quotes from this lab is printed by one of these commands.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from . import DATA, load_json
from .aiact import classify_feature
from .claims import find_overclaims
from .dpia import check_dpia
from .licenses import classify
from .matrix import check_matrix, render_matrix

NOTICE = ("This pack is evidence for review by accountable people. It is not a compliance claim, a certification "
          "or legal advice.")


def render_matrix_report(draft: bool) -> str:
    grants = load_json(DATA / "matrix" / ("grants-draft.json" if draft else "grants-reviewed.json"))
    permissions = load_json(DATA / "matrix" / "permissions.json")
    findings = check_matrix(grants, permissions)
    kinds = Counter(i["kind"] for i in grants["identities"])
    lines = [f"# Permission matrix ({'agent draft' if draft else 'reviewed'})", "",
             f"Identities: {kinds['person']} people, {kinds['agent']} agents; permissions in the catalogue: "
             f"{len(permissions['permissions'])}; findings: {len(findings)}", "", render_matrix(grants, permissions)]
    if findings:
        lines += ["", "| Rule | Subject | Finding |", "| --- | --- | --- |"]
        lines += [f"| {f.rule} | {f.subject} | {f.message} |" for f in findings]
    return "\n".join(lines)


def render_dpia(draft: bool) -> str:
    dpia = load_json(DATA / "dpia" / ("dpia-draft.json" if draft else "dpia-reviewed.json"))
    findings = check_dpia(dpia, load_json(DATA / "dpia" / "retention-policy.json"))
    lines = [f"# DPIA check: {dpia['title']}", "",
             f"Flows: {len(dpia['flows'])}; risks: {len(dpia['risks'])}; findings: {len(findings)}"
             + (f" ({', '.join(f'{r} {n}' for r, n in sorted(Counter(f.rule for f in findings).items()))})"
                if findings else "")]
    if findings:
        lines += ["", "| Rule | Subject | Finding |", "| --- | --- | --- |"]
        lines += [f"| {f.rule} | {f.subject} | {f.message} |" for f in findings]
    lines += ["", "| Flow | Data | Retention (days) | Residency | Minimisation |", "| --- | --- | ---: | --- | --- |"]
    for f in dpia["flows"]:
        lines.append(f"| {f['id']} | {f['data']} | {f['retention_days'] if f['retention_days'] is not None else '-'}"
                     f" | {f['residency'] or '-'} | {f['minimisation'] or '-'} |")
    return "\n".join(lines)


def render_licenses() -> str:
    policy = load_json(DATA / "licenses" / "license-policy.json")
    comps = load_json(DATA / "licenses" / "components.json")["components"]
    rows = [(c, *classify(c, policy)) for c in comps]
    n = Counter(d for _, d, _ in rows)
    lines = [f"# Licence scan ({policy['version']})", "",
             f"Components: {len(rows)}; allow {n['allow']}, review {n['review']}, deny {n['deny']}", "",
             "| Component | Origin | Licence | Decision | Reason |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {c['name']} | {c['origin']} | {c['license'] or '-'} | {d} | {r} |" for c, d, r in rows]
    return "\n".join(lines)


def render_aiact() -> str:
    dates = load_json(DATA / "aiact" / "dates.json")
    feats = load_json(DATA / "aiact" / "features.json")["features"]
    rows = [(f, classify_feature(f, dates["dates"])) for f in feats]
    n = Counter(c.tier for _, c in rows)
    order = ["prohibited", "high-risk", "transparency", "minimal", "outside the definition"]
    lines = ["# EU AI Act first-pass classification (the authors' reading; not legal advice)", "",
             "Tiers: " + ", ".join(f"{t} {n[t]}" for t in order), f"Dates: {dates['status']}.",
             f"Caveat: {dates['caveat']}", "",
             "| Feature | Status | Tier | Role | Basis | Applies from |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {f['id']} {f['name']} | {f['status']} | {c.tier} | {c.role} | {c.basis} | {c.applies_from or '-'} |"
              for f, c in rows]
    return "\n".join(lines)


def render_claims(draft: bool) -> str:
    path = DATA / "pack" / ("pack-draft.md" if draft else "pack-reviewed.md")
    found = find_overclaims(path.read_text(encoding="utf-8"))
    lines = [f"# Overclaims in {path.name}: {len(found)}"]
    if found:
        lines += ["", "| Line | Phrase | Sentence |", "| ---: | --- | --- |"]
        lines += [f"| {o.line} | {o.phrase} | {o.sentence} |" for o in found]
    return "\n".join(lines)


def render_pack() -> str:
    parts = ["# Relay governance pack (assembled by govpack)", "", NOTICE, "",
             render_matrix_report(False), "", render_dpia(False), "", render_licenses(), "", render_aiact(), "",
             render_claims(False)]
    return "\n".join(parts).replace("\n# ", "\n## ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lab 14.2 reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("matrix", "dpia", "claims"):
        sub.add_parser(name).add_argument("--draft", action="store_true")
    for name in ("licenses", "aiact", "pack"):
        sub.add_parser(name)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    print({"matrix": lambda: render_matrix_report(args.draft), "dpia": lambda: render_dpia(args.draft),
           "claims": lambda: render_claims(args.draft), "licenses": render_licenses, "aiact": render_aiact,
           "pack": render_pack}[args.cmd]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
