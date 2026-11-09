"""TODO 1: IDN001-IDN006 on hand-written credentials. IDN007-IDN010 are provided and tested here too."""

from datetime import date

import pytest
from conftest import POLICY

from agentsec.inventory import check_break_glass, check_credential, check_drills, check_federation, check_inventory

INV = {"people": ["sam.o", "tomas.b"], "drills": [], "credentials": []}


def cred(**changes):
    c = {"id": "C99", "agent": "eval-harvester", "system": "relay", "type": "relay-agent-token",
         "lifetime_seconds": 900, "bound_to_job": False, "stored": "none", "used_by": ["eval-harvester"],
         "owner": "tomas.b", "grants": ["tickets:read:support"], "needs": ["tickets:read:support"],
         "approval_counts": False, "can_merge": False, "bypass_branch_protection": False,
         "trust_subject": "repo:relay-example/relay:environment:eval-harvest", "attributable": True,
         "revocation_path": "ci-job"}
    c.update(changes)
    return c


def found(c):
    return [(f.rule, f.message) for f in check_credential(c, INV, POLICY)]


def test_a_clean_credential_has_no_findings():
    assert found(cred()) == []


@pytest.mark.parametrize("changes, expected", [
    ({"lifetime_seconds": None}, [("IDN001", "no expiry")]),
    ({"lifetime_seconds": 3601}, [("IDN001", "lifetime 3601 s, above 3600 s")]),
    ({"lifetime_seconds": 3600}, []),
    ({"lifetime_seconds": 86400, "bound_to_job": True}, []),
    ({"used_by": ["eval-harvester", "dataset-refresh", "eval-harvester"]},
     [("IDN002", "used by 2 agents: dataset-refresh, eval-harvester")]),
    ({"owner": None}, [("IDN003", "no owner recorded")]),
    ({"owner": "relay-bot"}, [("IDN003", "owner relay-bot is not a person")]),
    ({"approval_counts": True}, [("IDN004", "can approve (counts toward required reviews)")]),
    ({"can_merge": True, "bypass_branch_protection": True}, [("IDN004", "can merge and bypass branch protection")]),
    ({"grants": ["tickets:read:support", "tasks:export:support", "projects:read:x"]},
     [("IDN005", "2 grant(s) beyond need: tasks:export:support, projects:read:x")]),
    ({"stored": "ci-secret"}, [("IDN006", "stored as ci-secret")]),
])
def test_each_rule(changes, expected):
    assert found(cred(**changes)) == expected


def test_rules_come_in_order_and_carry_the_policy_severity():
    fs = check_credential(cred(lifetime_seconds=None, stored="file", owner=None, can_merge=True), INV, POLICY)
    assert [(f.rule, f.severity) for f in fs] == [("IDN001", "high"), ("IDN003", "high"), ("IDN004", "critical"),
                                                  ("IDN006", "high")]
    assert {f.credential for f in fs} == {"C99"} and {f.agent for f in fs} == {"eval-harvester"}


def test_provided_federation_drill_and_break_glass_rules():
    assert [f.message for f in check_federation(cred(trust_subject="repo:relay-example/*"), POLICY)] == [
        "wildcard in trust subject repo:relay-example/*"]
    assert check_federation(cred(type="service-token", trust_subject=None), POLICY) == []
    inv = {**INV, "drills": [{"id": "D", "path": "ci-job", "date": "2026-10-01", "result": "pass"}]}
    assert check_drills(cred(), inv, POLICY, date(2026, 12, 30)) == []
    assert len(check_drills(cred(), inv, POLICY, date(2027, 1, 1))) == 1  # 92 days later
    bg = {"permission_set": "X", "approval": "none", "session_hours": 8, "alert_rule": None, "usable_by_agents": True}
    assert check_break_glass(bg, POLICY)[0].message == (
        "approval none; sessions of 8 hours; no alert on use; usable by agents")


def test_check_inventory_orders_by_credential_then_rule():
    inv = {**INV, "credentials": [cred(id="C02", stored="file", attributable=False), cred(id="C01", owner=None)],
           "drills": [{"id": "D", "path": "ci-job", "date": "2027-01-06", "result": "pass"}],
           "break_glass": {"permission_set": "X", "approval": "two-person", "session_hours": 1,
                           "alert_rule": "DR-004", "usable_by_agents": False}}
    assert [(f.credential, f.rule) for f in check_inventory(inv, POLICY, date(2027, 1, 12))] == [
        ("C02", "IDN006"), ("C02", "IDN008"), ("C01", "IDN003")]


def test_replace_static_key_builds_the_registered_replacement():
    from conftest import RELAY
    from agentsec.inventory import replace_static_key
    from relay.audit import AgentRegistry
    agent = AgentRegistry.load(RELAY / "governance" / "agents.json").get("analytics-sync")
    old = cred(id="C06", agent="analytics-sync", type="service-token", lifetime_seconds=None, stored="file",
               grants=["projects:read:analytics", "tasks:export:analytics"], needs=["tasks:export:analytics"])
    new = replace_static_key(old, agent, "C06-R")
    assert new == {"id": "C06-R", "agent": "analytics-sync", "system": "relay", "type": "relay-agent-token",
                   "lifetime_seconds": 900, "bound_to_job": False, "stored": "none", "used_by": ["analytics-sync"],
                   "owner": "lena.k", "grants": ["tasks:export:analytics"], "needs": ["tasks:export:analytics"],
                   "approval_counts": False, "can_merge": False, "bypass_branch_protection": False,
                   "trust_subject": "arn:aws:sts::111122223333:assumed-role/relay-nonprod-agent-analytics-sync",
                   "attributable": True, "revocation_path": "ecs-task",
                   "note": "replaces C06 (service-token); exchanged at run time"}
    assert [f.rule for f in check_credential(new, {**INV, "people": ["lena.k"]}, POLICY)] == []


def test_replace_static_key_refuses_a_need_the_registry_does_not_grant():
    from conftest import RELAY
    from agentsec.inventory import replace_static_key
    from relay.audit import AgentRegistry
    agent = AgentRegistry.load(RELAY / "governance" / "agents.json").get("eval-harvester")
    with pytest.raises(ValueError, match="registry does not grant projects:read:support-inbox"):
        replace_static_key(cred(needs=["projects:read:support-inbox"]), agent, "C01-R")
