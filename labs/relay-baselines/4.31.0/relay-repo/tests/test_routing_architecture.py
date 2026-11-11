"""relay.routing's boundaries (4.28.0, ADR-042): standard library and itself only, no network, and nothing in Relay
imports it until the hooks are merged. Read with `ast`, like tests/test_architecture.py, which this file does not
change."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "relay" / "routing"


def imports():
    out = []
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                out += [(path.name, a.name) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                out.append((path.name, ("." * node.level) + (node.module or "")))
    return out


def test_the_package_has_its_four_modules():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == ["__init__", "costs", "policy", "quota"]


def test_routing_imports_only_the_standard_library_and_itself():
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    assert [(f, m) for f, m in imports() if not m.startswith(".") and m.split(".")[0] not in allowed] == []
    assert {m for _, m in imports() if m.startswith("..")} == set()


def test_routing_makes_no_network_calls_and_runs_no_shell():
    banned = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio", "subprocess"}
    assert [(f, m) for f, m in imports() if m.lstrip(".").split(".")[0] in banned] == []


def test_nothing_in_relay_imports_routing_yet():
    users = [p.name for p in sorted((ROOT / "src" / "relay").rglob("*.py")) if PACKAGE not in p.parents
             and any(s in p.read_text(encoding="utf-8") for s in ("relay.routing", "from ..routing", "from .routing"))]
    assert users == []
