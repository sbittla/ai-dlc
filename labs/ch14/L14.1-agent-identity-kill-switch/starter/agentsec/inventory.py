"""Credential inventory checks: policy agent-identity-policy-v1, rules IDN001-IDN010 (starter: TODOs).

An inventory lists every credential an agent uses, in every system (Relay, AWS, GitHub, the MCP query
tool), with what it grants, what the agent needs, how long it lives, where it is stored, who owns it and
whether its actions can be traced. The checks read only the inventory: they cannot see a credential
nobody recorded, which is why the inventory is built from the systems' own lists (see the README).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FEDERATED = frozenset({"relay-agent-token", "oidc-federated-role"})
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    credential: str
    agent: str
    message: str


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _f(policy: dict, rule: str, c: dict, message: str) -> Finding:
    return Finding(rule, policy["rules"][rule]["severity"], c["id"], c["agent"], message)


def check_credential(c: dict, inventory: dict, policy: dict) -> list[Finding]:
    """IDN001-IDN006 for one credential, in rule order. At most one finding per rule.

    IDN001  lifetime_seconds is None                                  -> "no expiry"
            lifetime_seconds > policy max_lifetime_seconds, unless bound_to_job
                                                                      -> "lifetime <n> s, above <max> s"
    IDN002  more than one distinct agent in used_by                   -> "used by <n> agents: a, b, c" (sorted)
    IDN003  owner is None                                             -> "no owner recorded"
            owner not in inventory["people"]                          -> "owner <owner> is not a person"
    IDN004  any of approval_counts, can_merge, bypass_branch_protection
                                                                      -> "can " + the true ones joined by " and ",
            named "approve (counts toward required reviews)", "merge", "bypass branch protection", in that order
    IDN005  grants not in needs, in grant order                       -> "<n> grant(s) beyond need: g1, g2"
    IDN006  stored is not "none"                                      -> "stored as <stored>"
    """
    raise NotImplementedError("TODO 1: IDN001-IDN006 for one credential")


def check_federation(c: dict, policy: dict) -> list[Finding]:
    """IDN007 (provided): a federated credential must name one exact workload subject."""
    if c["type"] not in FEDERATED:
        return []
    subject = c.get("trust_subject")
    if not subject:
        return [_f(policy, "IDN007", c, "no trust subject recorded")]
    if "*" in subject:
        return [_f(policy, "IDN007", c, f"wildcard in trust subject {subject}")]
    return []


def check_attribution(c: dict, policy: dict) -> list[Finding]:
    """IDN008 (provided): the credential's actions must name the agent and a person."""
    return [] if c["attributable"] else [_f(policy, "IDN008", c, "actions do not record the agent and a person")]


def check_drills(c: dict, inventory: dict, policy: dict, as_of: date) -> list[Finding]:
    """IDN009 (provided): a passing drill of this credential's revocation path within the policy's window."""
    window = policy["drill_max_age_days"]
    ok = [d for d in inventory.get("drills", []) if d["path"] == c["revocation_path"] and d["result"] == "pass"
          and 0 <= (as_of - date.fromisoformat(d["date"])).days <= window]
    if ok:
        return []
    return [_f(policy, "IDN009", c, f"no passing {c['revocation_path']} drill in the last {window} days")]


def check_break_glass(bg: dict, policy: dict) -> list[Finding]:
    """IDN010 (provided): one finding listing every problem with the break-glass permission set."""
    problems = []
    if bg["approval"] != "two-person":
        problems.append(f"approval {bg['approval']}")
    if bg["session_hours"] > 1:
        problems.append(f"sessions of {bg['session_hours']} hours")
    if not bg["alert_rule"]:
        problems.append("no alert on use")
    if bg["usable_by_agents"]:
        problems.append("usable by agents")
    if not problems:
        return []
    return [Finding("IDN010", policy["rules"]["IDN010"]["severity"], "break-glass", bg["permission_set"],
                    "; ".join(problems))]


def check_inventory(inventory: dict, policy: dict, as_of: date) -> list[Finding]:
    """Every rule on every credential, then the break-glass set. Ordered by credential, then rule."""
    out = []
    for c in inventory["credentials"]:
        found = (check_credential(c, inventory, policy) + check_federation(c, policy) + check_attribution(c, policy)
                 + check_drills(c, inventory, policy, as_of))
        out += sorted(found, key=lambda f: f.rule)
    return out + check_break_glass(inventory["break_glass"], policy)


def gate_status(findings: list[Finding]) -> int:
    """0 if no critical or high finding remains, else 1."""
    return 1 if any(SEVERITY_ORDER[f.severity] <= 1 for f in findings) else 0


def replace_static_key(c: dict, agent, new_id: str) -> dict:
    """The credential that replaces static credential `c`, for registered agent `agent` (a relay.audit
    AgentIdentity): a Relay agent token exchanged at run time. Raise ValueError if any of c's `needs` is not
    one of the agent's registered scopes, naming the first such need ("registry does not grant <need>").

    Fields: id new_id; agent agent.agent_id; system "relay"; type "relay-agent-token"; lifetime_seconds
    agent.max_ttl_seconds; bound_to_job False; stored "none"; used_by [agent.agent_id]; owner agent.owner;
    grants and needs: c's needs, in c's order; approval_counts, can_merge, bypass_branch_protection False;
    trust_subject agent.subject; attributable True; revocation_path agent.kind; note
    "replaces <c's id> (<c's type>); exchanged at run time".
    """
    raise NotImplementedError("TODO 7: replace a static key with a registered agent token")
