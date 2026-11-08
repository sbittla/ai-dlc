"""Specification tests for TODO 1-4, on inputs small enough to check by hand."""

from fitcheck.graph import Import, build_graph, imports_of
from fitcheck.rules import check_dependencies, check_layers, find_cycles

DEP_RULE = {"id": "FF005", "adr": "ADR-008", "adr_dir": "docs/adr"}
CYCLE_RULE = {"id": "FF006", "adr": "ADR-007"}


def targets(source, module="relay.service.app", is_package=False):
    return [i.target for i in imports_of(source, module, is_package)]


# ------------------------------------------------------------ TODO 1: imports_of

def test_plain_imports_one_per_name():
    assert targets("import json, urllib.request\nimport os.path as p\n") == ["json", "urllib.request", "os.path"]


def test_from_import_gives_the_module():
    assert targets("from datetime import date, timezone\n") == ["datetime"]


def test_relative_imports_resolve_against_the_package():
    src = "from . import directory\nfrom .ratelimit import RateLimiter\nfrom ..worker import TriageQueue\nfrom .. import __version__\n"
    assert targets(src) == ["relay.service", "relay.service.ratelimit", "relay.worker", "relay"]


def test_in_an_init_file_the_package_is_the_module_itself():
    assert targets("from .queue import Job\n", module="relay.worker", is_package=True) == ["relay.worker.queue"]


def test_imports_inside_functions_and_blocks_count_and_are_in_line_order():
    src = "def f():\n    import socket\n\nif True:\n    from ..worker.queue import Job\nimport json\n"
    found = imports_of(src, "relay.service.app", False)
    assert found == [Import(2, "socket"), Import(5, "relay.worker.queue"), Import(6, "json")]


def test_strings_and_dynamic_imports_are_not_imports():
    assert targets('import importlib\nimportlib.import_module("relay.worker.queue")\nx = "import socket"\n') == ["importlib"]


# ------------------------------------------------------------ TODO 2: check_layers

GRAPH = {
    "relay.api": [Import(3, "relay.models"), Import(4, "relay.worker")],
    "relay.service.app": [Import(1, "relay.worker"), Import(2, "relay.worker.queue")],
    "relay.worker.runner": [Import(5, "relay.worker.queue")],
}
LAYERS = [
    {"id": "FF001", "adr": "ADR-007", "from": ["relay.api"], "forbid": ["relay.worker.*"]},
    {"id": "FF002", "adr": "ADR-007", "from": ["relay.service.*"], "forbid": ["relay.worker.+"]},
]


def test_layer_findings_by_hand():
    found = check_layers(GRAPH, LAYERS)
    assert [(f.rule, f.module, f.line, f.message) for f in found] == [
        ("FF001", "relay.api", 4, "imports relay.worker"),          # ".*" includes the package itself
        ("FF002", "relay.service.app", 2, "imports relay.worker.queue"),  # ".+" only what is under it
    ]
    assert found[0].adr == "ADR-007"


def test_a_module_not_under_from_is_not_checked():
    assert check_layers(GRAPH, [{"id": "X", "adr": "A", "from": ["relay.models"], "forbid": ["relay.*"]}]) == []


# ------------------------------------------------------------ TODO 3: check_dependencies

PYPROJECT_NONE = '[project]\nname = "relay"\ndependencies = []\n'
PYPROJECT_HTTPX = '[project]\nname = "relay"\ndependencies = ["httpx==0.28.1"]\n'
ADR_OK = "# ADR-009 — x\nStatus: accepted\nDependency: httpx\n"


def deps(source, pyproject, adrs=None):
    files = {"src/relay/service/app.py": source, "pyproject.toml": pyproject, **(adrs or {})}
    return [f.message for f in check_dependencies(build_graph(files), files, DEP_RULE)]


def test_standard_library_and_own_package_are_fine():
    assert deps("from __future__ import annotations\nimport json\nfrom ..store import TaskStore\n", PYPROJECT_NONE) == []


def test_undeclared_and_unrecorded():
    assert deps("import requests\n", PYPROJECT_NONE) == ["imports requests: not in pyproject.toml and no accepted ADR"]


def test_declared_but_unrecorded():
    assert deps("import httpx\n", PYPROJECT_HTTPX) == ["imports httpx: no accepted ADR"]


def test_declared_and_recorded_passes_but_only_if_accepted():
    assert deps("import httpx\n", PYPROJECT_HTTPX, {"docs/adr/ADR-009.md": ADR_OK}) == []
    proposed = ADR_OK.replace("accepted", "proposed")
    assert deps("import httpx\n", PYPROJECT_HTTPX, {"docs/adr/ADR-009.md": proposed}) == ["imports httpx: no accepted ADR"]


def test_recorded_but_undeclared():
    assert deps("import httpx.client\n", PYPROJECT_NONE, {"docs/adr/ADR-009.md": ADR_OK}) == [
        "imports httpx: not in pyproject.toml"]


# ------------------------------------------------------------ TODO 4: find_cycles

def test_a_three_module_cycle_by_hand():
    graph = {
        "relay.service.app": [Import(1, "relay.worker"), Import(2, "relay")],
        "relay.worker": [Import(1, "relay.worker.runner")],
        "relay.worker.runner": [Import(9, "relay.service.app"), Import(3, "json")],
        "relay": [],
    }
    found = find_cycles(graph, CYCLE_RULE)
    assert [(f.module, f.line, f.message) for f in found] == [
        ("relay.service.app", 0, "cycle: relay.service.app -> relay.worker -> relay.worker.runner")]


def test_importing_an_ancestor_package_is_not_a_cycle():
    graph = {"relay.worker": [Import(1, "relay.worker.runner")],
             "relay.worker.runner": [Import(2, "relay.worker")]}
    assert find_cycles(graph, CYCLE_RULE) == []


def test_two_cycles_are_reported_in_order():
    graph = {"relay.b": [Import(1, "relay.a")], "relay.a": [Import(1, "relay.b")],
             "relay.d": [Import(1, "relay.c")], "relay.c": [Import(1, "relay.d")], "relay.e": []}
    assert [f.message for f in find_cycles(graph, CYCLE_RULE)] == ["cycle: relay.a -> relay.b",
                                                                   "cycle: relay.c -> relay.d"]
