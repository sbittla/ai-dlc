"""The permission matrix and its separation-of-duties checks (provided; a worked example).

GOV001  an agent holds a permission that is never for agents
GOV002  an agent has no accountable owner, or an owner who is not a person in the matrix
GOV003  a two-person permission is held by fewer than two people (so nobody can be the second person)
GOV004  a grant names a permission that is not in the catalogue
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    rule: str
    subject: str
    message: str


def check_matrix(grants: dict, permissions: dict) -> list[Finding]:
    catalogue = permissions["permissions"]
    never = set(permissions["never_for_agents"])
    people = {i["id"] for i in grants["identities"] if i["kind"] == "person"}
    out = []
    for i in grants["identities"]:
        if i["kind"] == "agent":
            out += [Finding("GOV001", i["id"], f"agent holds {p}") for p in i["grants"] if p in never]
            if i["owner"] not in people:
                out.append(Finding("GOV002", i["id"], "no accountable owner" if i["owner"] is None
                                   else f"owner {i['owner']} is not a person"))
        out += [Finding("GOV004", i["id"], f"unknown permission {p}") for p in i["grants"] if p not in catalogue]
    for p in permissions["two_person"]:
        holders = sorted(i["id"] for i in grants["identities"] if i["kind"] == "person" and p in i["grants"])
        if len(holders) < 2:
            out.append(Finding("GOV003", p, f"held by {len(holders)} person(s): {', '.join(holders) or 'nobody'}"))
    return out


def render_matrix(grants: dict, permissions: dict) -> str:
    perms = list(permissions["permissions"])
    extra = sorted({p for i in grants["identities"] for p in i["grants"]} - set(perms))
    cols = perms + extra
    lines = ["| Identity | Kind | Owner | " + " | ".join(cols) + " |",
             "| --- | --- | --- | " + " | ".join("---" for _ in cols) + " |"]
    for i in grants["identities"]:
        cells = ["x" if p in i["grants"] else "" for p in cols]
        lines.append(f"| {i['id']} | {i['kind']} | {i['owner'] or '-'} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
