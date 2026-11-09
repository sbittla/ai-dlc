"""Architecture fitness functions for ADR-007, ADR-009 and ADR-011, run with every other test.

These tests read the source with `ast`; they never import it. They check
static imports only: a dynamic import (importlib, __import__) or a network
call made through a subprocess is invisible to them. Lab 6.2 builds the
general tool, with a rules file, seeded violations and its known blind spots.

Rules (ADR-007, "Consequences"):
  AR1  Domain modules import neither relay.service nor relay.worker.
  AR2  relay.service imports the worker only through `relay.worker`, never its submodules.
  AR3  relay.worker imports nothing from relay.service.
  AR4  Only relay.service may import network modules; the domain and the worker make no network calls.
  AR5  Relay imports only the standard library and itself (pyproject: dependencies = []).
  AR6  relay.service imports the escalation engine only through `relay.escalation`, never its submodules
       (ADR-009), as AR2 does for the worker.

ADR-011 adds the engine's modules (hours, delivery, store, engine) to DOMAIN, so AR1 and AR4 cover them.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
DOMAIN = {"relay", "relay.api", "relay.duedates", "relay.models", "relay.roles", "relay.store", "relay.timezones",
          "relay.escalation", "relay.escalation.model", "relay.escalation.rules",
          "relay.escalation.evaluate", "relay.escalation.contract",
          "relay.escalation.hours", "relay.escalation.delivery", "relay.escalation.store", "relay.escalation.engine"}
NETWORK = {"socket", "ssl", "http", "urllib", "wsgiref", "socketserver", "smtplib", "ftplib", "asyncio",
           "xmlrpc", "requests", "httpx", "aiohttp", "urllib3"}


def module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports(path: Path) -> list[tuple[int, str]]:
    """(line, absolute module) for every static import in the file."""
    mod = module_name(path)
    package = mod if path.name == "__init__.py" else mod.rpartition(".")[0]
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            out.append((node.lineno, target))
    return out


GRAPH = {module_name(p): imports(p) for p in sorted(SRC.rglob("*.py"))}


def under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def violations(rule) -> list[str]:
    return [f"{mod}:{line} imports {target}" for mod, edges in GRAPH.items()
            for line, target in edges if rule(mod, target)]


def test_the_graph_covers_the_new_packages():
    assert {"relay.service.app", "relay.worker.queue", "relay.store"} <= set(GRAPH)


def test_every_escalation_module_is_in_the_domain_list():
    assert {m for m in GRAPH if under(m, "relay.escalation")} <= DOMAIN


def test_ar1_domain_does_not_depend_on_service_or_worker():
    assert violations(lambda m, t: m in DOMAIN and (under(t, "relay.service") or under(t, "relay.worker"))) == []


def test_ar2_service_uses_only_the_worker_public_interface():
    assert violations(lambda m, t: under(m, "relay.service") and t.startswith("relay.worker.")) == []


def test_ar3_worker_does_not_depend_on_service():
    assert violations(lambda m, t: under(m, "relay.worker") and under(t, "relay.service")) == []


def test_ar4_no_network_modules_outside_the_service():
    assert violations(lambda m, t: not under(m, "relay.service") and t.split(".")[0] in NETWORK) == []


def test_ar6_service_uses_only_the_escalation_public_interface():
    assert violations(lambda m, t: under(m, "relay.service") and t.startswith("relay.escalation.")) == []


def test_ar5_standard_library_only():
    allowed = set(sys.stdlib_module_names) | {"relay", "__future__"}
    assert violations(lambda m, t: t.split(".")[0] not in allowed) == []


@pytest.mark.parametrize("source, expected", [
    ("from ..worker.queue import TriageQueue\n", ["relay.service.app:1 imports relay.worker.queue"]),
    ("from ..worker import TriageQueue\n", []),
])
def test_the_rule_itself_catches_a_seeded_violation(tmp_path, monkeypatch, source, expected):
    fake = tmp_path / "relay" / "service"
    fake.mkdir(parents=True)
    (fake / "app.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SRC", tmp_path)
    graph = {module_name(p): imports(p) for p in tmp_path.rglob("*.py")}
    found = [f"{m}:{line} imports {t}" for m, e in graph.items() for line, t in e
             if under(m, "relay.service") and t.startswith("relay.worker.")]
    assert found == expected
