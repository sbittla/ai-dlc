"""Reports for Lab 12.1 (provided).

    python -m redteam.report incident              # the composite incident, from data/incident/timeline.json
    python -m redteam.report classes               # the threat model's attack classes and their labels
    python -m redteam.report matrix [--release R]  # the control matrix (default 4.26.0)
    python -m redteam.report gate [--release R]    # relay-coverage-gate-v2 on the matrix; exit 1 on FAIL
    python -m redteam.report g4 [--release R]      # Gate G4's adversarial row: the gate plus deployment
    python -m redteam.report domains               # what the failure of each failure domain does (4.26.0)
    python -m redteam.report alone                 # which classes each blocking control covers on its own
    python -m redteam.report all                   # everything above
"""

from __future__ import annotations

import argparse
import sys

from . import matrix as mx

SHORT = {"verified": "V", "failed": "F", "mitigating": "m", "latent": "L", "absent": "-"}


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
             "| Class | Effect | Channel | Technique | Harm | STRIDE | OWASP LLM | Agentic | ATLAS | Variants |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: |"]
    for c in data["classes"]:
        lines.append(f"| {c['id']} | {c['effect']} | {c['channel']} | {c['technique']} | {c['harm']} | "
                     f"{c['stride']} | {c['owasp_llm']} | {c['owasp_agentic']} | {c['atlas']} | {len(c['variants'])} |")
    return "\n".join(lines)


def render_matrix(release: str = "4.26.0") -> str:
    m = mx.verify(release)
    names = []
    for c in m.cells:
        if c.claimed not in names:
            names.append(c.claimed)
    cov = mx.coverage(m)
    lines = [f"Release {release}. V verified, F failed, m mitigating, L latent, - absent, blank not claimed.", "",
             "| Class | Harm | " + " | ".join(names) + " | Coverage |",
             "| --- | --- | " + " | ".join("---" for _ in names) + " | ---: |"]
    for cls in m.classes:
        row = {c.claimed: SHORT[c.status] for c in m.row(cls["id"])}
        lines.append(f"| {cls['id']} | {cls['harm']} | " + " | ".join(row.get(n, "") for n in names)
                     + f" | {cov[cls['id']]} |")
    counts = {s: sum(1 for c in m.cells if c.status == s) for s in SHORT}
    lines += ["", f"Cells: {len(m.cells)}; verified {counts['verified']}; failed {counts['failed']}; "
              f"mitigating {counts['mitigating']}; latent {counts['latent']}; absent {counts['absent']}."]
    lines += [f"Failed: {c.cls} {c.control} ({c.evidence})." for c in m.cells if c.status == "failed"]
    lines.append(f"Classes with coverage 1: {', '.join(k for k, v in cov.items() if v == 1) or 'none'}.")
    lines.append(f"Classes with coverage 0: {', '.join(k for k, v in cov.items() if v == 0) or 'none'}.")
    return "\n".join(lines)


def render_gate(release: str = "4.26.0") -> str:
    m = mx.verify(release)
    policy = mx.load("gate-policy.json")
    passed, reasons = mx.gate(m, policy)
    lines = [f"relay-coverage-gate-v2 on {release}: {'PASS' if passed else 'FAIL'}"]
    owners = policy["open_items_2027_02_12"] if release == "4.26.0" else {}
    for r in reasons:
        cid = r.split(":", 1)[0]
        item = owners.get(cid)
        lines.append(f"- {r}" + (f" (owner {item['owner']}, due {item['due']})" if item else ""))
    return "\n".join(lines)


def render_g4(release: str = "4.26.0") -> str:
    m = mx.verify(release)
    met, reasons = mx.g4_row(m, mx.load("gate-policy.json"))
    lines = [f"Gate G4 adversarial row on {release}: {'MET' if met else 'NOT MET'}"]
    lines += [f"- {r}" for r in reasons]
    return "\n".join(lines)


def render_domains() -> str:
    m = mx.verify("4.26.0")
    lines = ["Release 4.26.0: the failure of one failure domain, everything else intact.", "",
             "| Failure domain | Classes that newly fall below the policy | Left with no verified control |",
             "| --- | --- | --- |"]
    for domain, effect in mx.remove_domain(m, mx.load("gate-policy.json")).items():
        lines.append(f"| {domain} | {', '.join(effect['below']) or 'none'} | "
                     f"{', '.join(effect['uncovered']) or 'none'} |")
    worst = max(mx.remove_domain(m, mx.load("gate-policy.json")).items(), key=lambda kv: len(kv[1]["below"]))
    lines.append(f"\nThe widest failure domain is {worst[0]}: {len(worst[1]['below'])} of {len(m.classes)} classes.")
    return "\n".join(lines)


def render_alone() -> str:
    m = mx.verify("4.26.0")
    total = len(m.classes)
    lines = ["Release 4.26.0: each blocking control on its own.", "",
             "| Control | Classes it covers alone | Share |", "| --- | --- | ---: |"]
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
    parser.add_argument("what", choices=["incident", "classes", "matrix", "gate", "g4", "domains", "alone", "all"])
    parser.add_argument("--release", default="4.26.0")
    args = parser.parse_args(argv)
    parts = {
        "incident": lambda: render_incident(), "classes": lambda: render_classes(),
        "matrix": lambda: render_matrix(args.release), "gate": lambda: render_gate(args.release),
        "g4": lambda: render_g4(args.release), "domains": lambda: render_domains(), "alone": lambda: render_alone(),
    }
    chosen = list(parts) if args.what == "all" else [args.what]
    out = "\n\n".join(parts[name]() for name in chosen)
    sys.stdout.write(out + "\n")
    if args.what in ("gate", "g4"):
        return 0 if out.splitlines()[0].endswith(("PASS", " MET")) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
