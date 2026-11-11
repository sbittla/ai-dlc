"""A safety and security case, checked against the evidence it cites (added in 4.31.0; ADR-056).

The structure follows Claims-Arguments-Evidence: one top claim, broken into sub-claims, each supported by an
argument and, at the leaves, by evidence items. Each evidence item names what produces it (a test, a drill, a
measurement, a review) and the strength it must have: `verified` (run on this code), `deployed` (observed on the
running system) or `modelled`. Defeaters record known reasons a claim might be false; an open defeater is a gap
in the case, stated rather than hidden.

`check` compares the case with results produced by running its evidence, and lists every problem:

  undeveloped:<claim>        a claim with neither sub-claims nor evidence
  unknown_evidence:<id>      a claim cites evidence the case does not define
  no_result:<id>             the evidence's producer has no recorded result
  failing:<id>               the result is a fail
  too_weak:<id>              the result is weaker than required: modelled where verified is required, or
                             a test where an observation of the running system (deployed) is required
  open_defeater:<id>         a defeater is open against a claim
  approval:<problem>         an approved case needs two approvers, one from @relay/security, neither the owner

A case with no problems supports its top claim on the evidence given. It does not make the claim true: the case is
only as good as the claims someone thought to make, which is why a reviewer reads it, and why it is reviewed
again when the bot, its policy or its tools change.
"""

from __future__ import annotations

from .policy import _people_ok

ACCEPTS = {"modelled": {"modelled", "verified", "deployed"}, "verified": {"verified", "deployed"},
           "deployed": {"deployed"}}


def meets(required: str, status: str) -> bool:
    """Whether evidence of `status` meets `required`: deployed needs an observation of the running system, verified
    accepts that or a run on this code, and modelled accepts anything recorded."""
    return status in ACCEPTS.get(required, set())


def check(case: dict, results: dict[str, dict], people: set[str], teams: dict, owner: str) -> list[str]:
    problems: list[str] = []
    claims = {c["id"]: c for c in case.get("claims", [])}
    evidence = {e["id"]: e for e in case.get("evidence", [])}
    roots = [c for c in claims.values() if not c.get("parent")]
    if len(roots) != 1:
        problems.append(f"structure:needs exactly one top claim, found {len(roots)}")
    children = {cid: [c for c in claims.values() if c.get("parent") == cid] for cid in claims}
    for cid, c in sorted(claims.items()):
        cited = c.get("evidence", [])
        if not cited and not children[cid]:
            problems.append(f"undeveloped:{cid}")
        for eid in cited:
            if eid not in evidence:
                problems.append(f"unknown_evidence:{eid}")
    for eid, e in sorted(evidence.items()):
        r = results.get(e.get("ref", ""))
        if r is None:
            problems.append(f"no_result:{eid}")
            continue
        if r.get("result") != "pass":
            problems.append(f"failing:{eid}")
        if not meets(e.get("required_status", "verified"), r.get("status", "")):
            problems.append(f"too_weak:{eid}")
    for d in case.get("defeaters", []):
        if d.get("status") != "closed":
            problems.append(f"open_defeater:{d['id']}")
        elif not set(d.get("closed_by", [])) <= set(evidence):
            problems.append(f"unknown_evidence:{d['id']}")
    if case.get("status") == "approved":
        problems += [f"approval:{p}" for p in _people_ok(case.get("approvals", []), teams, owner, people)]
    return problems


def supported(case: dict, results: dict[str, dict]) -> dict[str, bool]:
    """Which claims hold on the evidence: a leaf needs all its evidence passing at the required strength, and a
    claim with sub-claims needs all of them and its own evidence."""
    claims = {c["id"]: c for c in case.get("claims", [])}
    evidence = {e["id"]: e for e in case.get("evidence", [])}
    blocked = {d["against"] for d in case.get("defeaters", []) if d.get("status") != "closed"}

    def ok(eid: str) -> bool:
        e, r = evidence.get(eid), results.get(evidence.get(eid, {}).get("ref", ""))
        return bool(e and r and r.get("result") == "pass" and
                    meets(e.get("required_status", "verified"), r.get("status", "")))

    memo: dict[str, bool] = {}

    def holds(cid: str) -> bool:
        if cid not in memo:
            c = claims[cid]
            kids = [k for k in claims.values() if k.get("parent") == cid]
            memo[cid] = (cid not in blocked and all(ok(e) for e in c.get("evidence", []))
                         and all(holds(k["id"]) for k in kids) and bool(kids or c.get("evidence")))
        return memo[cid]

    return {cid: holds(cid) for cid in sorted(claims)}
