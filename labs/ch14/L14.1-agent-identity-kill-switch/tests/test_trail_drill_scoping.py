"""TODO 4 (attribution), TODO 5 (revocation time) and TODO 6 (caller scoping), on small hand-made cases."""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import LAB_ROOT, RELAY

from agentsec.drill import Outcome, cloud_seconds, revocation_seconds
from agentsec.scoping import ScopedTool
from agentsec.trailcheck import attribution
from relay.audit import AgentRegistry
from relaymcp.db import open_readonly
from relaymcp.policy import AuditLog

REGISTRY = AgentRegistry.load(RELAY / "governance" / "agents.json")
T0 = datetime(2027, 1, 6, 10, 0, tzinfo=timezone.utc)


def rec(seq, **changes):
    r = {"seq": seq, "agent_id": "coding-session", "owner": "sam.o", "on_behalf_of": "priya.n",
         "action": "testdb.query", "detail": {}}
    r.update(changes)
    return r


def test_attribution_requires_a_registered_agent_its_owner_and_an_allowed_person():
    records = [rec(1), rec(2, on_behalf_of="tomas.b"), rec(3, owner="priya.n"), rec(4, agent_id=None),
               rec(5, agent_id="eval-harvester", owner="tomas.b", on_behalf_of="tomas.b"),
               rec(6, on_behalf_of=None), rec(7, action="killswitch.trip", on_behalf_of=None,
                                              detail={"actor": "detection:DR-001"}),
               rec(8, action="killswitch.restore", on_behalf_of=None, detail={})]
    a = attribution(records, REGISTRY)
    # 2: tomas.b is a person but not one of coding-session's delegators; 3: wrong owner; 4: no agent;
    # 6: nobody named; 8: a kill-switch record with no actor.
    assert (a.records, a.attributed, a.unattributed) == (8, 3, (2, 3, 4, 6, 8))


def o(client, seconds, accepted):
    return Outcome(client, T0 + timedelta(seconds=seconds), accepted, "ok" if accepted else "disabled")


@pytest.mark.parametrize("outcomes, expected", [
    ([o("a", -10, True), o("a", 2, True), o("a", 4, False), o("a", 6, False)], 4),
    ([o("a", 2, True), o("b", 3, False), o("a", 4, True), o("b", 8, False)], 8),   # b refused early, a later
    ([o("a", 2, True), o("a", 4, True)], None),                                    # never revoked in the window
    ([o("a", -2, True), o("a", 5, False)], 5),                                     # nothing accepted after alert
    ([o("a", 2, True), o("a", 4, False), o("a", 210, True), o("a", 212, False)], 212),
])
def test_revocation_seconds(outcomes, expected):
    assert revocation_seconds(outcomes, T0) == expected


def test_cloud_seconds_is_provided_and_takes_the_longest_branch():
    a = {"alert_to_trip": 4, "workflow_start": 15,
         "after_start": {"cloud_role": [["attach", 2], ["propagate", 30]], "ci-job": [["cancel", 10]],
                         "ecs-task": [["stop", 20]]}}
    assert (cloud_seconds(a, "ci-job", False), cloud_seconds(a, "ci-job", True), cloud_seconds(a, "ecs-task", True)) \
        == (29, 51, 51)


@pytest.fixture()
def tool():
    conn = open_readonly(LAB_ROOT / "vendor" / "relay-test.sql")
    return ScopedTool(conn, REGISTRY, AuditLog())


CLAIMS = {"sub": "coding-session", "obo": "priya.n", "scp": ["testdb:query"]}


def test_scope_and_limits_are_checked_before_anything_runs(tool):
    assert tool.handle({"template": "task_by_id", "params": {"task_id": 7}}, {**CLAIMS, "scp": []}, T0)["error"] \
        == "scope_missing"
    assert tool.handle({"template": "task_by_id", "params": {"task_id": 7}},
                       {"sub": "eval-harvester", "obo": "tomas.b", "scp": ["testdb:query"]}, T0)["error"] \
        == "no_tool_limits"
    assert tool.handle({"template": "nope"}, CLAIMS, T0)["error"] == "unknown_template"
    assert [e["outcome"] for e in tool.audit.entries] == ["scope_missing", "no_tool_limits", "unknown_template"]


def test_another_workspace_is_out_of_scope_however_it_is_named(tool):
    for req in ({"template": "tasks_by_project", "params": {"project_id": 3}},
                {"template": "webhook_failures", "params": {"workspace_id": 2, "min_attempts": 1}},
                {"template": "task_by_id", "params": {"task_id": 999}}):
        assert tool.handle(req, CLAIMS, T0)["error"] == "out_of_scope"
    ok = tool.handle({"template": "tasks_by_project", "params": {"project_id": 1}}, CLAIMS, T0)
    assert ok["ok"] and ok["row_count"] == 20 and ok["budget_remaining"] == 180
    assert tool.audit.entries[-1]["caller"] == "coding-session for priya.n"


def test_the_row_budget_is_shared_across_calls_and_resets_after_an_hour(tool):
    big = {"template": "tasks_by_project", "params": {"project_id": 1}, "limit": 50}
    rows = [tool.handle(big, CLAIMS, T0 + timedelta(seconds=n)).get("row_count") for n in range(9)]
    assert rows == [26, 26, 26, 26, 26, 26, 26, 18, None]  # 7 x 26 = 182; the 8th is cut to 18; then refused
    assert tool.handle(big, CLAIMS, T0 + timedelta(seconds=9))["error"] == "row_budget_exhausted"
    assert tool.handle(big, {**CLAIMS, "obo": "sam.o"}, T0)["row_count"] == 26  # another person's budget
    assert tool.handle(big, CLAIMS, T0 + timedelta(hours=1, seconds=1))["row_count"] == 26
