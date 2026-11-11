"""The case: bind each evidence item to a result, then check the case with Relay's checker.

TODO 3 `results`: the results dictionary `relay.maintenance.safety_case.check` reads.
"""

from __future__ import annotations

from relay.maintenance import safety_case

from .harness import POLICY, load


def results(adversarial: list, budget: list, drills: dict) -> dict[str, dict]:
    """TODO 3. One entry per evidence reference:

    - "adv:<id>" for each adversarial row: status "verified", result "pass" if its verdict is "held", else "fail";
    - "budget:<id>" for each budget row, the same way;
    - every entry of `drills` as it is (its own status and result).
    Nothing else: a reference with no entry is reported by the checker as `no_result`.
    """
    raise NotImplementedError("TODO 3: results")


def check(adversarial: list, budget: list) -> tuple[list[str], dict[str, bool]]:
    case = load("case-draft.json")
    res = results(adversarial, budget, load("drills.json"))
    people = set(POLICY.teams["@relay/maintainers"]) | {"aisha.r", "lena.k", "tomas.b"}
    return (safety_case.check(case, res, people, dict(POLICY.teams), POLICY.bot_owner),
            safety_case.supported(case, res))
