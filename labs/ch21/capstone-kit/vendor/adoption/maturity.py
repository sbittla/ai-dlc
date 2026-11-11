"""Readiness and maturity scored from evidence, not opinion (Chapter 20, Section 20.1).

A criterion is met when at least one admissible evidence item supports it. A team's level in a dimension is the
highest level L for which every criterion at levels 2 to L is met; level 1 needs nothing. There is no average
across dimensions: the profile is the result, and the weakest dimension is what an adoption plan must fix first.
Anyone who holds the same evidence register gets the same levels and the same reasons.
"""

from __future__ import annotations

import operator
from datetime import date

ADMISSIBLE = {"artifact", "measurement", "record", "survey"}
OPS = {"<=": operator.le, ">=": operator.ge}


def criterion_met(criterion: dict, items: list[dict], team: str, as_of: str) -> tuple[bool, str]:
    """Is `criterion` met for `team` on `as_of` (ISO date)? Return (met, reason).

    Candidates are the items whose "criterion" is the criterion's id and whose "team" is `team` or "*"
    (company-wide). An item is admissible when all of these hold, checked in this order, each failure giving the
    reason in brackets:
      - its type is not "opinion"                                   ["opinion is not evidence"]
      - its type is in the criterion's "accepts" list                ["<type> not accepted"]
      - it has a non-empty "ref" and "owner"                        ["no reference or owner"]
      - its date is not after as_of                                  ["dated after the assessment"]
      - it is at most the criterion's "max_age_days" old on as_of   ["older than <max_age_days> days"]
      - if the criterion has a "threshold" {field, op, value}, the item has that field and
        OPS[op](item[field], value) holds                            ["<field> <item value> fails <op> <value>"]
    Met: (True, "met by <ref>") for the first admissible candidate in date order, newest first.
    Not met with no candidates: (False, "no evidence"). Otherwise (False, the distinct reasons sorted and joined
    with "; ").
    """
    cands = [i for i in items if i["criterion"] == criterion["id"] and i["team"] in (team, "*")]
    if not cands:
        return False, "no evidence"
    day = date.fromisoformat(as_of)
    reasons = []
    for item in sorted(cands, key=lambda i: i["date"], reverse=True):
        if item["type"] == "opinion":
            reasons.append("opinion is not evidence")
            continue
        if item["type"] not in criterion["accepts"]:
            reasons.append(f"{item['type']} not accepted")
            continue
        if not item.get("ref") or not item.get("owner"):
            reasons.append("no reference or owner")
            continue
        when = date.fromisoformat(item["date"])
        if when > day:
            reasons.append("dated after the assessment")
            continue
        if (day - when).days > criterion["max_age_days"]:
            reasons.append(f"older than {criterion['max_age_days']} days")
            continue
        th = criterion.get("threshold")
        if th:
            got = item.get(th["field"])
            if got is None or not OPS[th["op"]](got, th["value"]):
                reasons.append(f"{th['field']} {got} fails {th['op']} {th['value']}")
                continue
        return True, f"met by {item['ref']}"
    return False, "; ".join(sorted(set(reasons)))


def team_level(model: dict, register: dict, team: str, dimension: str) -> tuple[int, str | None, str]:
    """Level of `team` in `dimension`, with the first unmet criterion and its reason (provided)."""
    criteria = sorted(model["dimensions"][dimension], key=lambda c: (c["level"], c["id"]))
    level = 1
    for lv in sorted({c["level"] for c in criteria}):
        for c in (c for c in criteria if c["level"] == lv):
            ok, why = criterion_met(c, register["evidence"], team, register["as_of"])
            if not ok:
                return level, c["id"], why
        level = lv
    return level, None, "all criteria met"


def assess(model: dict, register: dict) -> dict[str, dict[str, tuple[int, str | None, str]]]:
    """Every team in every dimension (provided)."""
    return {team: {dim: team_level(model, register, team, dim) for dim in model["dimensions"]}
            for team in register["teams"]}
