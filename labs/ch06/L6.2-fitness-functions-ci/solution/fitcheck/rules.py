"""Architecture rules as code. TODO 2-4 are yours in starter/.

Each rule has an ID (FF001-FF006) and the ADR it enforces, so a failing check
points at the decision it protects. Rules come from data/rules.json.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass

from .graph import Import


@dataclass(frozen=True)
class Finding:
    rule: str
    adr: str
    module: str
    line: int
    message: str


def matches(module: str, pattern: str) -> bool:
    """'x' matches x exactly; 'x.*' matches x and every module under it; 'x.+' only modules under it."""
    if pattern.endswith(".*"):
        base = pattern[:-2]
        return module == base or module.startswith(base + ".")
    if pattern.endswith(".+"):
        return module.startswith(pattern[:-2] + ".")
    return module == pattern


def matches_any(module: str, patterns) -> bool:
    return any(matches(module, p) for p in patterns)


def check_layers(graph: dict[str, list[Import]], layers: list[dict]) -> list[Finding]:
    """TODO 2. Layer rules (FF001-FF003 in data/rules.json).

    For each rule in `layers` (in order), for each module in the graph (sorted by name)
    that matches any of the rule's "from" patterns, report every import whose target
    matches any of its "forbid" patterns. One Finding per import, with the rule's "id"
    and "adr", the importing module, the import's line, and the message
    f"imports {target}". Use `matches_any`.
    """
    out = []
    for rule in layers:
        for mod in sorted(graph):
            if not matches_any(mod, rule["from"]):
                continue
            for imp in graph[mod]:
                if matches_any(imp.target, rule["forbid"]):
                    out.append(Finding(rule["id"], rule["adr"], mod, imp.line, f"imports {imp.target}"))
    return out


def check_network(graph: dict[str, list[Import]], rule: dict) -> list[Finding]:
    """FF004: network modules imported outside the modules allowed to use them (provided)."""
    out = []
    for mod in sorted(graph):
        if matches_any(mod, rule["allowed_in"]):
            continue
        for imp in graph[mod]:
            if imp.target.split(".")[0] in rule["modules"]:
                out.append(Finding(rule["id"], rule["adr"], mod, imp.line, f"imports network module {imp.target}"))
    return out


def declared_dependencies(pyproject_text: str) -> set[str]:
    """Distribution names in [project] dependencies, lower-cased, without versions (provided)."""
    deps = tomllib.loads(pyproject_text).get("project", {}).get("dependencies", [])
    return {re.split(r"[ <>=!~;\[]", d, maxsplit=1)[0].lower() for d in deps}


def adr_dependencies(files: dict[str, str], adr_dir: str) -> set[str]:
    """Names in 'Dependency: name' lines of ADRs under adr_dir whose Status is accepted (provided)."""
    named = set()
    for path, text in files.items():
        if not (path.startswith(adr_dir + "/") and path.endswith(".md")):
            continue
        if not re.search(r"^Status:\s*accepted\s*$", text, re.M | re.I):
            continue
        named |= {m.lower() for m in re.findall(r"^Dependency:\s*([A-Za-z0-9_.-]+)\s*$", text, re.M)}
    return named


def check_dependencies(graph: dict[str, list[Import]], files: dict[str, str], rule: dict,
                       package: str = "relay") -> list[Finding]:
    """TODO 3. FF005: every third-party import is declared and has an accepted ADR.

    A third-party import is one whose top-level name is not in sys.stdlib_module_names,
    not `package`, and not "__future__". For each module (sorted) and each such import,
    in order, report one Finding if the top-level name (lower-cased) is missing from
    `declared_dependencies(files["pyproject.toml"])`, from `adr_dependencies(files,
    rule["adr_dir"])`, or from both. The message is f"imports {top}: " followed by the
    missing parts joined with " and ": "not in pyproject.toml", "no accepted ADR".
    (Import names and distribution names can differ, as with `yaml` and PyYAML; this rule
    assumes they match and says so in the chapter.)
    """
    declared = declared_dependencies(files.get("pyproject.toml", ""))
    recorded = adr_dependencies(files, rule["adr_dir"])
    out = []
    for mod in sorted(graph):
        for imp in graph[mod]:
            top = imp.target.split(".")[0]
            if top in sys.stdlib_module_names or top in (package, "__future__"):
                continue
            missing = []
            if top.lower() not in declared:
                missing.append("not in pyproject.toml")
            if top.lower() not in recorded:
                missing.append("no accepted ADR")
            if missing:
                out.append(Finding(rule["id"], rule["adr"], mod, imp.line, f"imports {top}: " + " and ".join(missing)))
    return out


def find_cycles(graph: dict[str, list[Import]], rule: dict, package: str = "relay") -> list[Finding]:
    """TODO 4. FF006: import cycles among the package's own modules.

    Edges go from a module to each imported target that is a module in `graph` and is
    under `package`. Ignore an edge whose target is an ancestor package of the source
    (`relay.service.app` importing `relay` or `relay.service`): Python allows those.
    Find the strongly connected components with more than one module. Report one
    Finding per component, ordered by its smallest module name, with `module` that
    smallest name, line 0, and message "cycle: " + " -> ".join(sorted members).
    """
    edges = {m: sorted({i.target for i in imps if i.target in graph and matches(i.target, package + ".*")
                        and not m.startswith(i.target + ".")}) for m, imps in graph.items()}
    index, low, stack, on_stack, comps = {}, {}, [], set(), []
    counter = [0]

    def visit(v):  # Tarjan's algorithm
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in edges[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                comps.append(sorted(comp))

    for v in sorted(edges):
        if v not in index:
            visit(v)
    return [Finding(rule["id"], rule["adr"], c[0], 0, "cycle: " + " -> ".join(c)) for c in sorted(comps)]


def run_rules(graph, files, rules: dict) -> list[Finding]:
    """All rules, in rule order (provided)."""
    pkg = rules["package"]
    return (check_layers(graph, rules["layers"]) + check_network(graph, rules["network"])
            + check_dependencies(graph, files, rules["dependencies"], pkg) + find_cycles(graph, rules["cycles"], pkg))
