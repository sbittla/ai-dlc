"""relay.agents's boundaries (4.24.0, ADR-024): standard library, relay.audit and itself only; no network; nothing
imported from the service, the worker or the escalation engine. Read with `ast`, like tests/test_architecture.py,
which this file does not change."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "relay" / "agents"


def imports():
    out = []
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                out += [(path.name, a.name) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                out.append((path.name, ("." * node.level) + (node.module or "")))
    return out


def test_the_package_has_its_nine_modules():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == [
        "__init__", "approval", "boundary", "budget", "contracts", "loop", "memory", "session", "state", "tools"]


def test_agents_imports_only_the_standard_library_audit_and_itself():
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    bad = [(f, m) for f, m in imports()
           if not m.startswith(".") and m.split(".")[0] not in allowed]
    assert bad == []
    relative = {m for _, m in imports() if m.startswith("..")}
    assert relative == {"..audit"}


def test_agents_makes_no_network_calls_and_runs_no_shell():
    banned = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio", "subprocess"}
    assert [(f, m) for f, m in imports() if m.lstrip(".").split(".")[0] in banned] == []


def test_only_the_production_worker_package_imports_agents():
    """4.30.0 (ADR-049): relay.agentops runs agents as queue workers; nothing else in Relay imports the runtime."""
    users = []
    for path in sorted((ROOT / "src" / "relay").rglob("*.py")):
        if PACKAGE in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        if "relay.agents" in text or "from ..agents" in text or "from .agents" in text:
            users.append(path.relative_to(ROOT / "src" / "relay").parts[0])
    assert set(users) == {"agentops", "maintenance"}  # 4.31.0 (ADR-053): the maintenance bot


def test_the_helper_has_its_own_github_app_that_can_never_approve_or_merge():
    data = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))
    helper = next(a for a in data["agents"] if a["agent_id"] == "spec-to-pr-helper")
    coding = next(a for a in data["agents"] if a["agent_id"] == "coding-session")
    app = data["github_apps"][helper["github_app"]]
    assert helper["github_app"] != coding["github_app"]  # tripping one kill switch does not stop the other
    assert app["code_owner"] is False and app["bypass_branch_protection"] is False
    assert "administration" not in app["installation_permissions"]
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    protection = json.loads((ROOT / "governance" / "branch-protection.json").read_text(encoding="utf-8"))
    assert helper["github_app"] not in owners and protection["restrictions"]["apps"] == []


def test_the_helper_is_registered_with_one_scope_short_tokens_and_required_delegation():
    data = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))
    helper = next(a for a in data["agents"] if a["agent_id"] == "spec-to-pr-helper")
    assert helper["scopes"] == ["tasks:read:platform"] and helper["max_ttl_seconds"] == 900
    assert helper["delegation"] == "required" and helper["delegators"] == ["priya.n", "sam.o"]
    assert helper["cloud_role"] is None and helper["github_app"] == "relay-spec-to-pr"
    assert helper["subject"] == "repo:relay-example/relay:environment:spec-to-pr"
