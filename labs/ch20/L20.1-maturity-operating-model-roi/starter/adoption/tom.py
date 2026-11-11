"""Target operating model checks, TOM001-TOM006 (provided: a worked example, Chapter 20, Section 20.2).

The operating model says who is accountable for each shared capability, who approves changes to it and how its
work is funded. The checks encode separation of duties at the level of the organization, as Chapter 14's
permission matrix does for identities.
"""

from __future__ import annotations

from . import Finding

TWO_PERSON = {"CAP01", "CAP02"}      # the catalog and the policy need two approvers
NEEDS_VETO = {"CAP01", "CAP02"}      # security can stop a catalog or policy change
MEASUREMENT = "CAP08"


def check_tom(tom: dict) -> list[Finding]:
    """TOM001 one named accountable person; TOM002 no agent accountable and every approver a person; TOM003 the
    sponsor neither accountable for nor approving measurement; TOM004 two approvers for the catalogue and policy;
    TOM005 funded or within an existing role; TOM006 a veto held by someone on the security list."""
    out: list[Finding] = []
    people, agents = set(tom["people"]), set(tom["agents"])
    for cap in tom["capabilities"]:
        cid, acc = cap["id"], cap["accountable"]
        if not acc or acc not in people:
            out.append(Finding("TOM001", cid, f"no named accountable person ({acc or 'blank'})"))
        if acc in agents or any(a not in people for a in cap["approvers"]):
            out.append(Finding("TOM002", cid, "an agent, or anyone not a person, is accountable or approves"))
        if cid == MEASUREMENT and tom["sponsor"] in [acc, *cap["approvers"]]:
            out.append(Finding("TOM003", cid, "the sponsor is accountable for, or approves, measuring the programme"))
        if cid in TWO_PERSON and len(set(cap["approvers"])) < 2:
            out.append(Finding("TOM004", cid, "a single approver"))
        if cap["fte"] <= 0 and cid not in tom.get("within_existing_roles", []):
            out.append(Finding("TOM005", cid, "no funded effort and not assigned to an existing role"))
        if cid in NEEDS_VETO and not (set(cap["security_veto"]) & set(tom.get("security_people", []))):
            out.append(Finding("TOM006", cid, "nobody from security holds a veto"))
    return sorted(out, key=lambda f: (f.rule, f.subject))
