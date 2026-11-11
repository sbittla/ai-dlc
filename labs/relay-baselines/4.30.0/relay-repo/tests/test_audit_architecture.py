"""relay.audit's boundaries (4.23.0, ADR-020): standard library and itself only, no network, and nothing in it
depends on the service or the worker. Read with `ast`, like tests/test_architecture.py, which this file does
not change."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "relay" / "audit"


def imports():
    out = []
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                out += [(path.name, a.name) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                out.append((path.name, ("." * node.level) + (node.module or "")))
    return out


def test_the_package_exists_with_its_four_modules():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == ["__init__", "identity", "killswitch", "redact", "trail"]


def test_audit_imports_only_the_standard_library_and_itself():
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    bad = [(f, m) for f, m in imports() if not m.startswith(".") and m.split(".")[0] not in allowed]
    assert bad == []


def test_audit_makes_no_network_calls_and_does_not_depend_on_service_or_worker():
    network = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio"}
    assert [(f, m) for f, m in imports() if m.split(".")[0] in network] == []
    assert [(f, m) for f, m in imports() if "service" in m or "worker" in m] == []
