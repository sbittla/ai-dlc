"""The kill switch (4.23.0, ADR-022): automation may trip it; only two people together may restore it, and an
agent with a cloud role only under a new role or after its old credentials have expired."""

import pytest

from relay.audit import (AUDIENCE, AgentRegistry, AuditTrail, RestoreRefused, TokenRejected, TokenService,
                         quarantine_policy, restore, revoke_older_sessions_policy, trip, verify)
from relay.audit.killswitch import CLOUD_CREDENTIAL_MAX_SECONDS

from test_audit_identity import KEY, NOW, harvester_workload, person, registry_data, sandbox_workload


def setup():
    data = registry_data()
    data["agents"][1]["cloud_role"] = "arn:aws:iam::111122223333:role/relay-nonprod-sandbox"
    data["agents"][1]["github_app"] = "relay-agents"
    registry = AgentRegistry(data)
    svc = TokenService(registry, KEY, clock=lambda: NOW, new_id=lambda: "jti-1")
    trail = AuditTrail(clock=lambda: "2027-01-06T10:00:04Z")
    return registry, svc, trail


def test_tripping_refuses_the_agents_tokens_and_records_who_tripped_it():
    registry, svc, trail = setup()
    token, _ = svc.exchange(harvester_workload(), ["tickets:read:support"])
    result = trip(registry, trail, "eval-harvester", actor="detection:DR-001", reason="export burst", now=NOW)
    with pytest.raises(TokenRejected):
        svc.verify(token)
    rec = trail.records[-1]
    assert (rec["action"], rec["agent_id"], rec["owner"], rec["detail"]) == (
        "killswitch.trip", "eval-harvester", "tomas.b", {"actor": "detection:DR-001", "reason": "export burst",
                                                         "epoch": 2})
    assert result.record_hash == rec["hash"] and result.epoch == 2
    assert result.external_steps == (
        "relay: eval-harvester disabled; every token issued before epoch 2 is refused",
        "github: cancel running workflow runs in environment eval-harvest")


def test_an_ecs_agent_gets_the_quarantine_the_service_scale_down_and_its_github_tokens_revoked():
    registry, _, trail = setup()
    result = trip(registry, trail, "coding-session", actor="aisha.r", reason="drill", now=NOW)
    assert result.external_steps[1:] == (
        "aws: attach relay-nonprod-agent-quarantine to arn:aws:iam::111122223333:role/relay-nonprod-sandbox",
        "aws: set desired count 0 on ECS services tagged agent=coding-session, then stop its running tasks",
        "github: revoke relay-agents installation tokens issued to coding-session and suspend the installation")


def test_restoring_needs_two_different_people_and_never_revives_old_tokens():
    registry, svc, trail = setup()
    token, _ = svc.exchange(harvester_workload(), ["tickets:read:support"])
    trip(registry, trail, "eval-harvester", actor="detection:DR-001", reason="drill", now=NOW)
    for actor, reviewer in (("detection:DR-001", "sam.o"), ("sam.o", "sam.o"), ("sam.o", "relay-bot")):
        with pytest.raises(RestoreRefused):
            restore(registry, trail, "eval-harvester", actor=actor, reviewed_by=reviewer, now=NOW)
    assert not registry.get("eval-harvester").enabled
    restore(registry, trail, "eval-harvester", actor="sam.o", reviewed_by="priya.n", now=NOW + 60)
    assert registry.get("eval-harvester").enabled
    with pytest.raises(TokenRejected) as exc:
        svc.verify(token)
    assert exc.value.code == "revoked"
    assert [r["action"] for r in trail.records] == ["killswitch.trip", "killswitch.restore"]
    assert verify(trail.records).ok


def test_an_agent_with_a_cloud_role_cannot_be_restored_where_copied_credentials_still_prove_it():
    registry, svc, trail = setup()
    trip(registry, trail, "coding-session", actor="aisha.r", reason="copied credentials", now=NOW)
    with pytest.raises(RestoreRefused):
        restore(registry, trail, "coding-session", actor="sam.o", reviewed_by="priya.n",
                now=NOW + CLOUD_CREDENTIAL_MAX_SECONDS - 1)
    # Under a new role, a proof signed with the old role's copied credentials names the old subject.
    new = "arn:aws:sts::111122223333:assumed-role/relay-nonprod-sandbox-2"
    restore(registry, trail, "coding-session", actor="sam.o", reviewed_by="priya.n", now=NOW + 60, new_subject=new,
            new_cloud_role="arn:aws:iam::111122223333:role/relay-nonprod-sandbox-2")
    with pytest.raises(TokenRejected) as exc:
        svc.exchange(sandbox_workload(), ["testdb:query"], subject=person())
    assert exc.value.code == "unknown_workload"
    assert trail.records[-1]["detail"]["new_subject"] is True


def test_waiting_out_the_credential_lifetime_also_allows_a_restore():
    registry, _, trail = setup()
    trip(registry, trail, "coding-session", actor="aisha.r", reason="drill", now=NOW)
    restore(registry, trail, "coding-session", actor="sam.o", reviewed_by="priya.n",
            now=NOW + CLOUD_CREDENTIAL_MAX_SECONDS)
    assert registry.get("coding-session").enabled


def test_the_quarantine_policy_denies_everything_and_the_session_policy_is_time_bound():
    assert quarantine_policy()["Statement"] == [
        {"Sid": "AgentQuarantined", "Effect": "Deny", "Action": "*", "Resource": "*"}]
    stmt = revoke_older_sessions_policy("2027-01-06T10:00:04Z")["Statement"][0]
    assert stmt["Effect"] == "Deny" and stmt["Condition"] == {
        "DateLessThan": {"aws:TokenIssueTime": "2027-01-06T10:00:04Z"}}


def test_tripping_an_unknown_agent_raises():
    registry, _, trail = setup()
    with pytest.raises(KeyError):
        trip(registry, trail, "nobody", actor="aisha.r", reason="typo")
    assert trail.records == []
    assert AUDIENCE == "relay-token-exchange"
