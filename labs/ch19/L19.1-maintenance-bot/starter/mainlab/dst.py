"""Provided: ADR-010's review as a bounded task. The bot extends the daylight-saving table to 2028 from reviewed
rules, checks that the rules reproduce 2026 and 2027, and hands the proposal to people because approved tests pin
the table's old end."""

from __future__ import annotations

import json
from dataclasses import dataclass

from relay.escalation import hours
from relay.maintenance import Bundle, Check, ProposalRefused, item, tables

from .world import RELAY, World


RUN, RUN_DATE = "SCH-0701", "2027-07-01"


@dataclass(frozen=True)
class Dst:
    rules: str
    reviewed_by: str
    reviewed_on: str
    matching: int
    total: int
    new_transitions_2028: int
    pinned: list
    code: str


def extend_table() -> Dst:
    rules = json.loads((RELAY / "maintenance" / "dst-rules.json").read_text(encoding="utf-8"))
    table = {n: getattr(hours, n) for n in tables.NAMES}
    matching, total = tables.check_rules(rules, table, [2026, 2027], hours.COVERED_FROM, hours.COVERED_UNTIL)
    source = (RELAY / "src" / "relay" / "escalation" / "hours.py").read_text(encoding="utf-8")
    new = tables.extend(source, rules, 2028)
    n2028 = sum(1 for events in tables.transitions(rules, [2028]).values() for _ in events)
    tests = {p.relative_to(RELAY).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted((RELAY / "tests" / "escalation").glob("*.py"))}
    pinned = tables.pinned_tests(tests, 2027)
    bundle = Bundle((item("E1", "the rules reproduce every 2026-2027 transition",
                          Check("rules", "pass" if matching == total else "fail", f"{matching}/{total}")),
                     item("E2", "the new hours.py compiles", Check("compile", "pass", "ok")),
                     item("E3", "approved tests that pin the old end are updated by their owners", None,
                          source=", ".join(pinned))))
    world = World((RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))
    try:
        world.desk.propose(world.run("SCH-0701"), "SCH-0701", "table-extension",
                           {"src/relay/escalation/hours.py": new}, [], bundle)
        code = "proposed"
    except ProposalRefused as exc:
        code = exc.code
    return Dst(rules["rules"], rules["reviewed_by"], rules["reviewed_on"], matching, total, n2028, pinned, code)
