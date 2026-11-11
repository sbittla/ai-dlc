"""relay.agentops's boundaries (4.30.0, ADR-049 to ADR-051), read with `ast` like tests/test_architecture.py, which
this file does not change: the standard library and Relay's own packages only, no network module anywhere, and
a sandbox child that imports nothing from Relay (it runs with no `relay` on its path)."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "relay" / "agentops"
NETWORK = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio", "ftplib", "xmlrpc"}


def imports(path):
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append(("." * node.level) + (node.module or ""))
    return out


def test_the_package_has_its_modules():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == [
        "__init__", "effects", "gateway", "jobs", "registry_state", "resilience", "sandbox", "sandbox_child", "tools",
        "worker"]


def test_agentops_imports_only_the_standard_library_and_relay():
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    bad = [(p.name, m) for p in PACKAGE.glob("*.py") for m in imports(p)
           if not m.startswith(".") and m.split(".")[0] not in stdlib]
    assert bad == []


def test_agentops_imports_no_network_module():
    assert [(p.name, m) for p in PACKAGE.glob("*.py") for m in imports(p) if m.lstrip(".").split(".")[0] in NETWORK] \
        == []


def test_the_sandbox_child_imports_nothing_from_relay():
    assert all(not m.startswith(".") and m.split(".")[0] in sys.stdlib_module_names | {"__future__"}
               for m in imports(PACKAGE / "sandbox_child.py"))


def test_only_the_sandbox_starts_processes():
    users = sorted(p.name for p in (ROOT / "src" / "relay").rglob("*.py") if "subprocess" in imports(p))
    assert users == ["sandbox.py"]


def test_the_production_helper_declares_its_code_running_tool_untrusted():
    from relay.agentops.tools import PRODUCTION_HELPER_TOOLS, RUN_CODE
    assert PRODUCTION_HELPER_TOOLS["run_tests"].untrusted_result and RUN_CODE.untrusted_result
    assert {n for n, c in PRODUCTION_HELPER_TOOLS.items() if c.effect == "external"} == {"open_pull_request"}


def test_no_agent_registry_entry_changed():
    data = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))
    assert [a["agent_id"] for a in data["agents"]] == ["analytics-sync", "ci-failure-triage", "coding-session",
                                                        "dataset-refresh", "eval-harvester", "maintenance-bot",
                                                        "spec-to-pr-helper",
                                                        "triage-worker"]
