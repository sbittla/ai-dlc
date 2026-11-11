"""The committed agent registry and the GitHub side of "agents cannot approve or merge" (4.23.0, ADR-020)."""

import json
import re
from pathlib import Path

from relay.audit import FORBIDDEN_SCOPES, AgentRegistry, validate

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))


def test_the_registry_loads_with_no_problems():
    assert validate(DATA) == []
    registry = AgentRegistry(DATA)
    assert [a.agent_id for a in registry.agents()] == [
        "analytics-sync", "ci-failure-triage", "coding-session", "dataset-refresh", "eval-harvester",
        "maintenance-bot", "spec-to-pr-helper",
        "triage-worker"]


def test_every_agent_has_a_person_as_owner_short_tokens_and_no_forbidden_or_export_scope_it_does_not_need():
    registry = AgentRegistry(DATA)
    for a in registry.agents():
        assert a.owner in registry.people and a.max_ttl_seconds <= 900
        assert not a.scopes & FORBIDDEN_SCOPES
    exporters = {a.agent_id for a in registry.agents() if any(s.startswith("tasks:export") for s in a.scopes)}
    assert exporters == {"analytics-sync"}
    assert registry.get("eval-harvester").scopes == {"tickets:read:support"}


def test_ci_subjects_name_one_protected_environment_and_cloud_roles_match_their_subjects():
    for a in DATA["agents"]:
        if a["kind"] == "ci-job":
            assert re.fullmatch(r"repo:relay-example/relay:environment:[a-z-]+", a["subject"])
        if a["cloud_role"] and a["kind"] == "ecs-task":
            assert a["subject"].rsplit("/", 1)[1] == a["cloud_role"].rsplit("/", 1)[1]


def test_the_agents_github_app_is_never_a_code_owner_and_never_bypasses_protection():
    gh = DATA["github"]
    assert gh["code_owner"] is False and gh["bypass_branch_protection"] is False
    assert "administration" not in gh["installation_permissions"]
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert gh["app"] not in owners and "relay-bot" not in owners
    protection = json.loads((ROOT / "governance" / "branch-protection.json").read_text(encoding="utf-8"))
    reviews = protection["required_pull_request_reviews"]
    assert reviews["require_code_owner_reviews"] and reviews["require_last_push_approval"]
    assert protection["enforce_admins"]["enabled"]
    # Merging a pull request is a push to main: only maintainers may push, and no app is on the list.
    assert protection["restrictions"] == {"users": [], "teams": ["maintainers"], "apps": []}
    assert DATA["agents"][[a["agent_id"] for a in DATA["agents"]].index("coding-session")]["github_app"] == gh["app"]


def test_the_coding_session_tool_limits_cover_the_query_tool():
    limits = AgentRegistry(DATA).get("coding-session").tool_limits["relay-db-readonly"]
    assert limits == {"workspaces": [1], "rows_per_hour": 200}
