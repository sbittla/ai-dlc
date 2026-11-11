"""Measuring the controls and the bot, with Chapter 7's statistics.

TODO 5 `paired`: the 60 historical updates under the old rule and under relay-maintenance-policy-v1, compared on
the same updates with an exact McNemar test. `month` (provided) reports the bot's first month and the T4 criteria.
"""

from __future__ import annotations

from dataclasses import dataclass

from relay.maintenance import eligibility, mcnemar_exact, metrics, runs_needed, verdict

from .world import POLICY, load

WIDENED = "2027-05-10"  # the day the old bot's rule began merging minor updates


@dataclass(frozen=True)
class Paired:
    updates: int
    old_reached: list
    new_reached: list
    b: int          # reached production under the old rule only
    c: int          # under the new policy only
    p: float
    old_auto_merged: int
    new_to_people: int
    stopped_by: dict


def old_rule_reaches(u: dict) -> bool:
    """Under the old rule a regression reached production whatever the route: auto-merged patches (and minors
    from 10 May) and the minors people merged by hand alike, because neither looked at defaults."""
    return u["regression"]


def new_policy_stop(u: dict) -> str | None:
    """Which control of the new policy stops a regression from reaching all users, or None."""
    if not u["regression"]:
        return None
    if u["default_change"]:
        return "pinned-defaults"
    if u["guard_visible"]:
        return "guard"
    return None


def paired(history: list[dict]) -> Paired:
    """TODO 5. For each update: did a regression reach all users under the old rule (`old_rule_reaches`) and under
    the new policy (a regression that `new_policy_stop` returns None for)? b counts updates bad only under the old
    rule, c only under the new; p is `mcnemar_exact(b, c)`.

    old_auto_merged: updates the old rule merged with no person (every patch, and minors from WIDENED on).
    new_to_people: updates the new policy sends to @relay/security (every minor, and every sensitive package).
    stopped_by: {control: number of updates it stopped}, over the regressions the new policy stops.
    """
    old = [u["update"] for u in history if old_rule_reaches(u)]
    new = [u["update"] for u in history if u["regression"] and new_policy_stop(u) is None]
    b = sum(1 for u in history if u["update"] in old and u["update"] not in new)
    c = sum(1 for u in history if u["update"] in new and u["update"] not in old)
    stops: dict[str, int] = {}
    for u in history:
        s = new_policy_stop(u)
        if s:
            stops[s] = stops.get(s, 0) + 1
    auto = sum(1 for u in history if u["bump"] == "patch" or (u["bump"] == "minor" and u["date"] >= WIDENED))
    people = sum(1 for u in history if u["bump"] != "patch" or u["sensitive"])
    return Paired(len(history), old, new, b, c, mcnemar_exact(b, c), auto, people, dict(sorted(stops.items())))


def month() -> tuple[list, dict]:
    """Provided. The bot's metrics per task type for 9 June to 9 July 2027, and the T4 criteria for each."""
    log, evidence = load("outcomes.json"), load("evidence.json")
    rows, verdicts = [], {}
    for name, t in POLICY.task_types.items():
        m = metrics(log, name)
        rows.append(m)
        verdicts[name] = (t.tier, verdict(eligibility(m, t.reads_untrusted, evidence, evidence["as_of"])))
    return rows, verdicts


def clean_runs_for(upper: float = 0.05) -> int:
    return runs_needed(upper)
