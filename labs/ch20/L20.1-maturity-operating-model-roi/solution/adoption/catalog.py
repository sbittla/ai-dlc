"""The approved tool and MCP catalog and the acceptable-use policy (Chapter 20, Sections 20.2 and 20.4).

The catalogue extends Chapter 3's MCP allowlist and Chapter 13's AI components record to the AI tools people use
for company work: coding agents, chat assistants, completion, tool servers and agents that run unattended. Relay's
product components (its hosted models and registered agents) stay in its AI components record and registry. It is checked against Relay's own
records, so that the company's list and a repository's pins cannot drift apart unnoticed.
"""

from __future__ import annotations

import re

from . import Finding

LIVE = {"approved", "trial"}
ATTENDED_TRIGGERS = {"person", "agent-session"}  # a person starts the work, or a session a person started


def check_catalog(catalog: dict, relay_mcp: dict, relay_components: dict, relay_agents: dict, as_of: str,
                  security_people: list[str], cases: list[dict]) -> list[Finding]:
    """Return findings CAT001-CAT007 and CAT009, sorted by rule then subject (the tool id, or the server name for
    the second CAT006 case). Dates are ISO strings and compare as text.

    security_people comes from the operating model, never from the catalogue being checked. cases is the safety
    and security case register. An entry is live when its status is in LIVE.

    CAT001 owner blank or not in catalog["people"]                                   (every entry)
    CAT002 live entry whose security_approver is blank, not in security_people, or is the entry's requested_by
           or owner
    CAT003 max_data_class not in catalog["data_classes"] (any case); or "Restricted" (any case) on an entry whose
           "external" is true; or an entry with no boolean "external" (every entry)
    CAT004 status "prohibited" with no "alternative", or an alternative that is not an approved entry
    CAT005 live entry whose review_by is before as_of
    CAT006 live tool server (kind "mcp-server", or any entry with a "launch") with no launch {command, args,
           sha256} or whose sha256 is not 64 lowercase
           hex characters, or, when Relay's AI components list a tool server with the entry's id, a launch whose
           command, args or sha256 differ from that record; and, for each server in Relay's .mcp.json
           ("mcpServers"), no live entry with that id whose launch command and args equal the server's (subject:
           the server name)
    CAT007 live entry that runs unattended, unless: its "safety_case" is the id of a case in `cases` whose
           "subject" is the entry's id, with status "approved" and at least two distinct approvers, all of them in
           catalog["people"], at least one in security_people and none the entry's owner; and its
           "registry_identity" is an agent in Relay's governance/agents.json whose agent_id or "catalogue_entry" is
           the entry's id and whose owner is the entry's owner. An entry runs unattended when "runs_unattended" is
           true, its kind is "autonomous-agent", or any of its "triggers" is outside ATTENDED_TRIGGERS. A live entry
           with no "triggers", no boolean "runs_unattended", or "runs_unattended" false while a trigger says
           otherwise is also a CAT007 finding.
    CAT009 an entry whose reviewed_on is after the catalogue's approved_on (it cannot have been in that version)
    """
    out: list[Finding] = []
    people = set(catalog["people"])
    security = set(security_people)
    classes = {c.lower() for c in catalog.get("data_classes", [])}
    tools = {t["id"]: t for t in catalog["tools"]}
    reviewed = {s["name"]: s for s in relay_components.get("tool_servers", [])}
    agents = {a["agent_id"]: a for a in relay_agents.get("agents", [])}
    approved_cases = {c["id"]: c for c in cases if c.get("status") == "approved"}
    for t in catalog["tools"]:
        tid, live = t["id"], t["status"] in LIVE
        if not t.get("owner") or t["owner"] not in people:
            out.append(Finding("CAT001", tid, "no accountable owner"))
        if live:
            sa = t.get("security_approver") or ""
            if not sa or sa not in security or sa in (t.get("requested_by"), t.get("owner")):
                out.append(Finding("CAT002", tid, f"security approval missing or not independent ({sa or 'blank'})"))
        if str(t.get("max_data_class", "")).strip().lower() not in classes:
            out.append(Finding("CAT003", tid, f"unknown data class {t.get('max_data_class')!r}"))
        elif not isinstance(t.get("external"), bool):
            out.append(Finding("CAT003", tid, "does not say whether it runs outside the company's accounts"))
        elif str(t.get("max_data_class", "")).strip().lower() == "restricted" and t["external"]:
            out.append(Finding("CAT003", tid, "Restricted data allowed in a tool outside the company's accounts"))
        if t["status"] == "prohibited":
            alt = tools.get(t.get("alternative") or "")
            if not alt or alt["status"] != "approved":
                out.append(Finding("CAT004", tid, "prohibited with no approved alternative"))
        if live and t["review_by"] < as_of:
            out.append(Finding("CAT005", tid, f"review was due {t['review_by']}"))
        if live and (t["kind"] == "mcp-server" or "launch" in t):
            launch = t.get("launch") or {}
            if not all(launch.get(k) for k in ("command", "args", "sha256")) or \
                    not re.fullmatch(r"[0-9a-f]{64}", launch["sha256"]):
                out.append(Finding("CAT006", tid, "launch not pinned"))
            elif tid in reviewed:
                rec = reviewed[tid]
                if (launch["command"], list(launch["args"]), launch["sha256"]) != \
                        (rec["command"], list(rec["args"]), rec["sha256"]):
                    out.append(Finding("CAT006", tid, "launch differs from Relay's reviewed record"))
        declared = t.get("runs_unattended")
        triggers = t.get("triggers")
        by_trigger = bool(triggers) and any(x not in ATTENDED_TRIGGERS for x in triggers)
        unattended = declared is True or t["kind"] == "autonomous-agent" or by_trigger
        if live and (not triggers or not isinstance(declared, bool) or (declared is False and by_trigger)):
            out.append(Finding("CAT007", tid, "triggers missing, or runs_unattended missing or contradicted"))
        elif live and unattended:
            case = approved_cases.get(t.get("safety_case") or "")
            approvers = set(case.get("approved_by", [])) if case else set()
            case_ok = (bool(case) and case.get("subject") == tid and len(approvers) >= 2 and approvers <= people
                       and bool(approvers & security) and t["owner"] not in approvers)
            agent = agents.get(t.get("registry_identity") or "")
            agent_ok = bool(agent) and agent.get("owner") == t["owner"] and \
                tid in (agent.get("agent_id"), agent.get("catalogue_entry"))
            if not case_ok or not agent_ok:
                out.append(Finding("CAT007", tid, "no approved safety case or registry identity for this tool"))
        if t.get("reviewed_on", "") > catalog["approved_on"]:
            out.append(Finding("CAT009", tid, f"reviewed {t['reviewed_on']}, after the catalogue was approved "
                                              f"on {catalog['approved_on']}"))
    for name, server in sorted(relay_mcp.get("mcpServers", {}).items()):
        t = tools.get(name)
        launch = (t or {}).get("launch") or {}
        if not t or t["status"] not in LIVE or (launch.get("command"), list(launch.get("args") or [])) != \
                (server.get("command"), list(server.get("args") or [])):
            out.append(Finding("CAT006", name, "server in Relay's .mcp.json is not in the catalogue as launched"))
    return sorted(out, key=lambda f: (f.rule, f.subject))


def check_aup(aup_text: str, sections: list[str], catalog_version: str) -> list[Finding]:
    """CAT008: the acceptable-use policy names the catalog version it governs and has every section (provided)."""
    out: list[Finding] = []
    if f"Catalog: {catalog_version}." not in aup_text:
        out.append(Finding("CAT008", "aup", f"does not name catalog {catalog_version}"))
    headings = {re.sub(r"^\d+\.\s*", "", h.strip()) for h in re.findall(r"^##\s+(.+)$", aup_text, re.MULTILINE)}
    missing = [s for s in sections if s not in headings]
    if missing:
        out.append(Finding("CAT008", "aup", "missing sections: " + ", ".join(missing)))
    return out
