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
    raise NotImplementedError("TODO 2: implement check_catalog")


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
