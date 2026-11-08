"""Read the four artifacts of a spec-first slice into comparable facts. Nothing is imported or run.

- spec:     specs/<slice>/spec.md      version, criterion IDs, data-rule fields, rejection codes, statuses
- contract: the JSON Schema it names  version, fields and their JSON types, enums tied to code constants
- code:     src/relay/escalation/      SPEC_VERSION, dataclass fields and annotations, tuple constants
- tests:    tests/escalation/          test names (criterion IDs) and the spec version each module declares

Code is read with `ast`, so a drift check never executes the code it checks.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SPEC_GLOB = "specs/*/spec.md"
PACKAGE = Path("src/relay/escalation")
TESTS = Path("tests/escalation")
CRITERION_TEST = re.compile(r"^test_([A-Z]+)_AC(\d+)(?:_|$)")
ENUMS = {"STATUSES": "Status", "ERROR_CODES": "Code"}  # code constant -> the spec's Behavior table


@dataclass
class Facts:
    """Everything the comparisons need. Missing artifacts leave their fields empty."""

    spec_version: str = ""
    contract_version: str = ""
    code_version: str = ""
    test_versions: dict[str, str] = field(default_factory=dict)  # test module -> declared spec version
    criteria: tuple[str, ...] = ()  # spec order
    tested: dict[str, tuple[str, ...]] = field(default_factory=dict)  # criterion ID -> test names
    data_rules: dict[str, str] = field(default_factory=dict)  # "Def.field" -> classification
    spec_tables: dict[str, tuple[str, ...]] = field(default_factory=dict)  # "Status"/"Code" -> values
    contract_fields: dict[str, str] = field(default_factory=dict)  # "Def.field" -> JSON type, e.g. "integer"
    contract_enums: dict[str, tuple[str, ...]] = field(default_factory=dict)  # code constant -> values
    code_fields: dict[str, str] = field(default_factory=dict)  # "Class.field" -> JSON type
    code_constants: dict[str, tuple[str, ...]] = field(default_factory=dict)  # name -> values


def json_type(schema: dict) -> str:
    """'integer', 'array', 'object', 'string|null', ... for one contract property."""
    if "$ref" in schema:
        return "object"
    t = schema.get("type", "any")
    return "|".join(sorted(t)) if isinstance(t, list) else t


PY_TYPES = {"int": "integer", "str": "string", "bool": "boolean", "float": "number", "datetime": "string"}


def annotation_type(text: str) -> str:
    """The JSON type a Python annotation serialises to: 'int' -> 'integer', 'str | None' -> 'null|string'."""
    parts = [p.strip() for p in text.split("|")]
    out = set()
    for p in parts:
        base = p.split("[", 1)[0]
        if p == "None":
            out.add("null")
        elif base in ("tuple", "list", "frozenset", "set"):
            out.add("array")
        else:
            out.add(PY_TYPES.get(base, "object"))
    return "|".join(sorted(out))


def _spec(repo: Path, facts: Facts) -> Path | None:
    found = sorted(repo.glob(SPEC_GLOB))
    if not found:
        return None
    text = found[0].read_text(encoding="utf-8")
    m = re.search(r"^Version: (\S+)$", text, re.M)
    facts.spec_version = m.group(1) if m else ""
    facts.criteria = tuple(re.findall(r"^### (ESC-AC\d+)\s*$", text, re.M))
    rules = text.split("\n## Data rules", 1)[-1].split("\n## ", 1)[0] if "\n## Data rules" in text else ""
    for m in re.finditer(r"^\| `([A-Za-z]+\.[a-z_]+)` \| ([A-Za-z]+) \|", rules, re.M):
        facts.data_rules[m.group(1)] = m.group(2)
    behavior = text.split("\n## Behavior", 1)[-1].split("\n## ", 1)[0] if "\n## Behavior" in text else ""
    mode = None
    for line in behavior.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else None
        if cells is None:
            mode = None
        elif cells[0] in ("Code", "Status"):
            mode = cells[0]
            facts.spec_tables.setdefault(mode, ())
        elif mode and cells[0].startswith("`"):
            facts.spec_tables[mode] += (cells[0].strip("`"),)
    m = re.search(r"^Contract: (\S+)$", text, re.M)
    return found[0].parent / m.group(1) if m else None


def _contract(path: Path | None, facts: Facts) -> None:
    if path is None or not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    facts.contract_version = str(data.get("x-spec-version", ""))
    for name, d in data.get("$defs", {}).items():
        for prop, schema in d.get("properties", {}).items():
            facts.contract_fields[f"{name}.{prop}"] = json_type(schema)
            if "x-relay-constant" in schema:
                facts.contract_enums[schema["x-relay-constant"]] = tuple(schema.get("enum", ()))


def _code(repo: Path, facts: Facts, contract_defs: set[str]) -> None:
    pkg = repo / PACKAGE
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name == "SPEC_VERSION" and isinstance(node.value, ast.Constant):
                    facts.code_version = str(node.value.value)
                elif isinstance(node.value, ast.Tuple) and all(isinstance(e, ast.Constant) for e in node.value.elts):
                    facts.code_constants[name] = tuple(e.value for e in node.value.elts)
            if isinstance(node, ast.ClassDef) and node.name in contract_defs:
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        facts.code_fields[f"{node.name}.{item.target.id}"] = annotation_type(
                            ast.unparse(item.annotation))


def _tests(repo: Path, facts: Facts) -> None:
    tested: dict[str, list[str]] = {}
    for path in sorted((repo / TESTS).glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        doc = ast.get_docstring(tree) or ""
        m = re.search(r"^Spec version: (\S+)$", doc, re.M)
        facts.test_versions[path.name] = m.group(1) if m else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                m = CRITERION_TEST.match(node.name)
                if m:
                    tested.setdefault(f"{m.group(1)}-AC{m.group(2)}", []).append(node.name)
    facts.tested = {k: tuple(v) for k, v in sorted(tested.items())}


def extract(repo: Path) -> Facts:
    repo = Path(repo)
    facts = Facts()
    contract_path = _spec(repo, facts)
    _contract(contract_path, facts)
    _code(repo, facts, {f.split(".")[0] for f in facts.contract_fields})
    _tests(repo, facts)
    return facts
