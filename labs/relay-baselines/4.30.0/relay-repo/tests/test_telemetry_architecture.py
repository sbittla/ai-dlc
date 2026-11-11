"""relay.telemetry's boundaries (4.27.0, ADR-036), read with `ast` like tests/test_architecture.py, which this file
does not change: standard library, relay.audit, relay.escalation's public interface and itself; no network; and it
depends on neither the service, the worker nor the agent runtime. Only relay.service may send (AR4)."""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "relay"
PACKAGE = SRC / "telemetry"
NETWORK = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "asyncio", "subprocess"}


def imports(folder: Path):
    out = []
    for path in sorted(folder.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                out += [(path.name, a.name) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                out.append((path.name, ("." * node.level) + (node.module or "")))
    return out


def test_the_package_has_its_modules():
    assert sorted(p.stem for p in PACKAGE.glob("*.py")) == [
        "__init__", "alerting", "detection", "fitness", "genai", "logs", "metrics", "monitor", "otlp", "redact",
        "runs", "semconv", "slo", "trace", "worker"]


def test_telemetry_imports_only_the_standard_library_audit_escalation_and_itself():
    allowed_relay = {"..audit.redact", "..audit", "..escalation", "..", "."}
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    bad = [(f, m) for f, m in imports(PACKAGE)
           if not (m in allowed_relay or (m.startswith(".") and not m.startswith("..")) or m.split(".")[0] in stdlib)]
    assert bad == []


def test_telemetry_makes_no_network_calls():
    assert [(f, m) for f, m in imports(PACKAGE) if m.lstrip(".").split(".")[0] in NETWORK] == []


def test_telemetry_depends_on_no_process_package():
    assert [(f, m) for f, m in imports(PACKAGE) if any(p in m for p in ("service", "worker", "agents"))] == []


def test_the_worker_and_the_agent_runtime_do_not_import_telemetry():
    users = [(folder.name, f) for folder in (SRC / "worker", SRC / "agents", SRC / "escalation", SRC / "audit")
             for f, m in imports(folder) if "telemetry" in m]
    assert users == []


def test_only_the_pager_in_the_service_imports_urllib():
    users = sorted({f for f, m in imports(SRC / "service") if m.split(".")[0] == "urllib"})
    assert users == ["pager.py"]
