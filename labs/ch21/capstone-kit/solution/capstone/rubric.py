"""The rubric scorer (TODO 3 in starter/): grading levels, ceilings from the evidence, gates and individuals.

The panel scores each rubric dimension from 0 to 100 and names the evidence items the score rests on. The
scorer does not second-guess the panel's judgement, but it will not let a score rise above what the evidence
can carry:

    RB001  a dimension scored with no evidence cited counts as 0
    RB002  a cited item has a blocking finding: the dimension is capped at 74 (below Acceptable)
    RB003  a cited item, or a required item the dimension rests on, is missing: capped at 59 (below Needs work)
    RB004  the panel found a limitation the team had not stated: the total is capped at 89 (below Excellent)
    RB005  a gate failed: the team's level is Fail, whatever the score
    RB006  a member could not explain and modify the part drawn for them: that member fails, whatever the
           team's level ("a team grade cannot lift an individual who cannot explain the system")

Levels: Excellent 90-100, Acceptable 75-89, Needs work 60-74 (a conditional pass, with five working days to
remediate), Fail below 60 or any gate failed.
"""

from __future__ import annotations

from .evidence import Result, tracks

CAP_BLOCKED = 74
CAP_MISSING = 59
CAP_UNSTATED = 89
GATES = ("security", "reproducibility", "explain", "disclosure", "hygiene")


def level(total: float) -> str:
    for lv in tracks()["levels"]:
        if total >= lv["min"]:
            return lv["name"]
    return "Fail"


def ceilings(res: Result) -> dict[str, tuple[int, list[str]]]:
    """For each dimension of the pack's track: the highest score its required evidence allows, and why.
    A required item the dimension rests on that is missing caps it at 59; one with a blocking finding at 74."""
    spec = tracks()["tracks"][res.pack["track"]]
    optional = {r["id"] for r in spec["requirements"] if r.get("optional")}
    out = {}
    for dim in spec["dimensions"]:
        cap, why = 100, []
        for rid in dim["requirements"]:
            state = res.requirement_state.get(rid, "missing")
            if state == "missing" and rid not in optional:
                cap = min(cap, CAP_MISSING)
                why.append(f"{rid} missing")
            elif state == "blocked":
                cap = min(cap, CAP_BLOCKED)
                why.append(f"{rid} has blocking findings")
        out[dim["id"]] = (cap, why)
    return out


def score(scores: dict, res: Result) -> dict:
    spec = tracks()["tracks"][scores["track"]]
    dims = {d["id"]: d for d in spec["dimensions"]}
    if set(scores["dimensions"]) != set(dims):
        raise ValueError(f"dimensions must be exactly {sorted(dims)}")
    if sum(d["weight"] for d in dims.values()) != 100:
        raise ValueError("track weights do not sum to 100")
    ceil = ceilings(res)
    pack_items = {i["id"] for i in res.pack.get("items", [])}
    rows, notes = [], []
    total = 0.0
    for did, d in dims.items():
        entry = scores["dimensions"][did]
        raw = entry.get("score", 0)
        cap, why = ceil[did]
        why = list(why)
        cited = entry.get("evidence", [])
        if not cited:
            cap, why = 0, ["RB001 no evidence cited"]
        for e in cited:
            if e not in pack_items:
                cap = min(cap, CAP_MISSING)
                why.append(f"RB003 {e} is not in the pack")
            elif not res.item_ok.get(e, False):
                cap = min(cap, CAP_BLOCKED)
                why.append(f"RB002 {e} has blocking findings")
        final = min(raw, cap)
        rows.append({"id": did, "weight": d["weight"], "raw": raw, "cap": cap, "final": final, "why": why})
        total += d["weight"] * final / 100
    total = round(total, 1)
    if scores.get("limitations_found_by_panel", 0) and total > CAP_UNSTATED:
        notes.append(f"RB004 the panel found {scores['limitations_found_by_panel']} unstated limitation(s): "
                     f"total {total} capped at {CAP_UNSTATED}")
        total = float(CAP_UNSTATED)
    members = scores.get("members", [])
    gates = dict(scores.get("gates", {}))
    gates["explain"] = "pass" if members and all(m.get("explain") == "pass" for m in members) else "fail"
    open_high = [f.where for f in res.findings if f.code == "EV011" and "RT005" in f.message]
    if open_high:
        gates["security"] = "fail"
        notes.append(f"RB005 security gate: open critical or high red-team finding in {', '.join(open_high)}")
    team_gates_failed = [g for g in GATES if g != "explain" and gates.get(g) != "pass"]
    team_level = "Fail" if team_gates_failed else level(total)
    if team_gates_failed:
        notes.append(f"RB005 gate(s) failed: {', '.join(team_gates_failed)}")
    people = []
    for m in members:
        if m.get("explain") != "pass":
            people.append((m["id"], "Fail", "RB006 could not explain and modify the part drawn"))
        else:
            people.append((m["id"], team_level, ""))
    outcome = {"Excellent": "pass", "Acceptable": "pass",
               "Needs work": "conditional pass: five working days to remediate, then re-scored",
               "Fail": "fail"}[team_level]
    return {"rows": rows, "total": total, "level": team_level, "outcome": outcome, "gates": gates,
            "notes": notes, "people": people}
