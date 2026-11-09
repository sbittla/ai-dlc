"""Reports for Lab 12.1 (provided).

    python -m redteam.report incident              # the composite incident, from data/incident/timeline.json
    python -m redteam.report classes               # the threat model's attack classes and their labels
    python -m redteam.report matrix [--release R]  # the verified control matrix (default 4.26.0)
    python -m redteam.report gate [--release R]    # relay-coverage-gate-v1 on the matrix
    python -m redteam.report removeone             # what removing each control alone does (4.26.0)
    python -m redteam.report alone                 # which classes each control covers on its own (4.26.0)
    python -m redteam.report all                   # everything above
"""

from __future__ import annotations

import argparse
import sys

from . import matrix as mx

SHORT = {"verified": "V", "failed": "F", "mitigating": "m", "absent": "-"}


def render_incident() -> str:
    inc = mx.load("incident/timeline.json")
    lines = [f"# {inc['title']} (composite)", ""]
    lines += [f"- {e['at'].replace('T', ' ').replace('Z', ' UTC')}  {e['event']}" for e in inc["events"]]
    lines += ["", f"Contact details in the image address: {inc['affected_contacts']}, "
              f"from {inc['affected_customers']} customers."]
    return "\n".join(lines)


def render_classes() -> str:
    data = mx.load("classes.json")
    lines = [f"Catalogue: {data['catalogue']}, {len(data['classes'])} classes.", "",
             "| Class | Effect | Channel | Technique | Harm | STRIDE | OWASP LLM | Agentic | ATLAS |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in data["classes"]:
        lines.append(f"| {c['id']} | {c['effect']} | {c['channel']} | {c['technique']} | {c['harm']} | "
                     f"{c['stride']} | {c['owasp_llm']} | {c['owasp_agentic']} | {c['atlas']} |")
    return "\n".join(lines)


def render_matrix(release: str = "4.26.0") -> str:
    m = mx.verify(release)
    names = []
    for c in m.cells:
        if c.claimed not in names:
            names.append(c.claimed)
    cov = mx.coverage(m)
    lines = [f"Release {release}. V verified, F failed, m mitigating only, - absent, blank not claimed.", "",
             "| Class | Harm | " + " | ".join(names) + " | Coverage |",
             "| --- | --- | " + " | ".join("---" for _ in names) + " | ---: |"]
    for cls in m.classes:
        row = {c.claimed: SHORT[c.status] for c in m.row(cls["id"])}
        lines.append(f"| {cls['id']} | {cls['harm']} | " + " | ".join(row.get(n, "") for n in names)
                     + f" | {cov[cls['id']]} |")
    verified = sum(1 for c in m.cells if c.status == "verified")
    failed = [c for c in m.cells if c.status == "failed"]
    lines += ["", f"Cells: {len(m.cells)}; verified {verified}; failed {len(failed)}; "
              f"mitigating {sum(1 for c in m.cells if c.status == 'mitigating')}; "
              f"absent {sum(1 for c in m.cells if c.status == 'absent')}."]
    lines += [f"Failed: {c.cls} {c.control} ({c.evidence})." for c in failed]
    single = [cid for cid, n in cov.items() if n == 1]
    none = [cid for cid, n in cov.items() if n == 0]
    lines.append(f"Classes with one verified control: {', '.join(single) or 'none'}.")
    lines.append(f"Classes with no verified control: {', '.join(none) or 'none'}.")
    return "\n".join(lines)


def render_gate(release: str = "4.26.0") -> str:
    m = mx.verify(release)
    passed, reasons = mx.gate(m, mx.load("gate-policy.json"))
    lines = [f"relay-coverage-gate-v1 on {release}: {'PASS' if passed else 'FAIL'}"]
    lines += [f"- {r}" for r in reasons]
    return "\n".join(lines)


def render_removeone() -> str:
    m = mx.verify("4.26.0")
    lines = ["Release 4.26.0: remove one control, keep the rest.", "",
             "| Removed | Classes that fall below the policy | Classes left with no verified control |",
             "| --- | --- | --- |"]
    for name, effect in mx.remove_one(m, mx.load("gate-policy.json")).items():
        lines.append(f"| {name} | {', '.join(effect['below']) or 'none'} | {', '.join(effect['uncovered']) or 'none'} |")
    without_recall = mx.shortfalls(m, mx.load("gate-policy.json"), frozenset({"recall_taint"}))
    lines += ["", "Without recall_taint (the first coverage run, before ADR-034 added RECALL_MEMORY): "
              + ", ".join(f"{cid} {have} of {need}" for cid, have, need in without_recall) + "."]
    return "\n".join(lines)


def render_alone() -> str:
    m = mx.verify("4.26.0")
    total = len(m.classes)
    lines = ["Release 4.26.0: each blocking control on its own.", "",
             "| Control | Classes it covers alone | Share of the 14 classes |", "| --- | --- | ---: |"]
    names = []
    for c in m.cells:
        if c.status == "verified" and c.claimed not in names:
            names.append(c.claimed)
    for name in names:
        covered = mx.only(m, name)
        lines.append(f"| {name} | {', '.join(covered)} | {len(covered)} of {total} |")
    best = max(len(mx.only(m, n)) for n in names)
    lines.append(f"\nThe widest single control covers {best} of {total} classes.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m redteam.report")
    parser.add_argument("what", choices=["incident", "classes", "matrix", "gate", "removeone", "alone", "all"])
    parser.add_argument("--release", default="4.26.0")
    args = parser.parse_args(argv)
    parts = {
        "incident": lambda: render_incident(), "classes": lambda: render_classes(),
        "matrix": lambda: render_matrix(args.release), "gate": lambda: render_gate(args.release),
        "removeone": lambda: render_removeone(), "alone": lambda: render_alone(),
    }
    chosen = list(parts) if args.what == "all" else [args.what]
    out = "\n\n".join(parts[name]() for name in chosen)
    sys.stdout.write(out + "\n")
    if args.what == "gate":
        return 0 if "PASS" in out.splitlines()[0] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
