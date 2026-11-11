"""Provided: print the adversarial suite, the budget scenarios and the case check.

    python -m caselab.report adversarial|budget|case|all
"""

from __future__ import annotations

import sys

from . import adversarial, budget, case


def render_adversarial(rows=None) -> str:
    rows = rows or adversarial.run_all()
    out = ["| Record | Asks for (inert placeholder) | Outcome | Audited refusals | Verdict | Claim |",
           "| --- | --- | --- | ---: | --- | --- |"]
    out += [f"| {r.rid} | {r.asks} | {r.outcome} | {r.audited} | {r.verdict} | {r.claim} |" for r in rows]
    out.append(f"Held: {sum(r.verdict == 'held' for r in rows)} of {len(rows)}.")
    return "\n".join(out)


def render_budget(rows=None) -> str:
    rows = rows or budget.run_all()
    out = ["| Scenario | What happens | Outcome | Spent | Items done | Verdict |", "| --- | --- | --- | ---: | ---: | --- |"]
    out += [f"| {r.sid} | {r.what} | {r.outcome} | ${r.usd:.4f} | {r.done} | {r.verdict} |" for r in rows]
    out.append(f"Held: {sum(r.verdict == 'held' for r in rows)} of {len(rows)}.")
    return "\n".join(out)


def render_case() -> str:
    adv, bud = adversarial.run_all(), budget.run_all()
    problems, supported = case.check(adv, bud)
    return "\n".join([f"Problems: {len(problems)}: {', '.join(problems)}.",
                      "Claims supported: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in supported.items())
                      + ".",
                      f"Approvable: {'yes' if not problems else 'no'}."])


SECTIONS = {"adversarial": render_adversarial, "budget": render_budget, "case": render_case}


def main(argv: list[str]) -> int:
    for n in (list(SECTIONS) if not argv or argv[0] == "all" else argv):
        print(f"## {n}\n{SECTIONS[n]()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
