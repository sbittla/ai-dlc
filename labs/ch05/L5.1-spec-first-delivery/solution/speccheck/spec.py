"""Parse a spec package (spec.md, tasks.md, the contract) and the PRD it comes from.

spec.md format (see templates/spec.md):

    # Spec — <title>
    Spec: ESC-SPEC-1                  <- header fields, one per line, before the first "## "
    Version: 1.0.0
    ...
    ## <Section>                      <- the nine required sections, in any order
    ### SEC-01 — <title>              <- under "Security constraints": Source:, Checks:, Statement:
    ### ESC-AC08                      <- under "Acceptance criteria": Requirement:, Coverage:, Criterion:, Deferred:
    | `Rule.rule_id` | Internal | … | <- under "Data rules": one row per field
    Contract: contracts/<file>.json   <- under "Contracts"; Outbound: names the documents sent for delivery

tasks.md format: "Spec: <ID>@<version>" in the header, then one "### Tnn — <title>"
block per task with Checks:, Depends on:, Files:, Risk:, Sensitive:, Untrusted input:, Tier:, Why:.
A field written "–" or left out is empty.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^### (\S+)(?: — (.*))?$")
FIELD = re.compile(r"^([A-Z][A-Za-z -]*): (.*)$")
EMPTY = {"", "–", "-", "none"}


def _list(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip() not in EMPTY)


def _fields(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        m = FIELD.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _blocks(body: str) -> list[tuple[str, str, dict[str, str], int]]:
    """(id, title, fields, line offset) for each "### " block in a section body."""
    out, current = [], None
    for n, line in enumerate(body.splitlines()):
        m = HEADING.match(line)
        if m:
            current = [m.group(1), m.group(2) or "", [], n]
            out.append(current)
        elif current is not None:
            current[2].append(line)
    return [(i, t, _fields(lines), n) for i, t, lines, n in out]


def _table(body: str) -> list[list[str]]:
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("|") and not set(line) <= set("|-: "):
            rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


@dataclass(frozen=True)
class Criterion:
    id: str
    requirement: str
    coverage: str
    text: str
    deferred: str


@dataclass(frozen=True)
class Constraint:
    id: str
    title: str
    sources: tuple[str, ...]
    checks: tuple[str, ...]
    statement: str


@dataclass(frozen=True)
class Spec:
    path: Path
    header: dict[str, str]
    sections: dict[str, str]
    criteria: tuple[Criterion, ...]
    constraints: tuple[Constraint, ...]
    data_rules: dict[str, str]  # field -> classification
    contract_path: str | None
    outbound: tuple[str, ...]
    codes: tuple[str, ...]  # rejection codes in the Behavior tables
    statuses: tuple[str, ...]  # evaluation statuses in the Behavior tables

    @property
    def id(self) -> str:
        return self.header.get("Spec", "")

    @property
    def version(self) -> str:
        return self.header.get("Version", "")

    def ids(self) -> set[str]:
        return {c.id for c in self.criteria} | {c.id for c in self.constraints}


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    checks: tuple[str, ...]
    depends: tuple[str, ...]
    files: tuple[str, ...]
    risk: str
    sensitive: str
    untrusted: str
    tier: str
    why: str


@dataclass(frozen=True)
class TaskList:
    path: Path
    spec_ref: str
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Contract:
    path: Path
    version: str
    definitions: dict[str, dict] = field(default_factory=dict)  # name -> its "properties"

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(f"{d}.{p}" for d, props in self.definitions.items() for p in props)


@dataclass(frozen=True)
class Prd:
    version: str
    requirements: tuple[str, ...]
    criteria: dict[str, tuple[str, str]]  # criterion id -> (requirement id, text)


def _split_sections(text: str) -> tuple[list[str], dict[str, str]]:
    head, sections, name = [], {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            sections[name] = ""
        elif name is None:
            head.append(line)
        else:
            sections[name] += line + "\n"
    return head, sections


def load_spec(spec_dir: Path) -> Spec:
    path = Path(spec_dir) / "spec.md"
    head, sections = _split_sections(path.read_text(encoding="utf-8"))
    header = _fields(head)
    criteria = tuple(
        Criterion(i, f.get("Requirement", ""), f.get("Coverage", ""), f.get("Criterion", ""), f.get("Deferred", ""))
        for i, _, f, _ in _blocks(sections.get("Acceptance criteria", "")))
    constraints = tuple(
        Constraint(i, t, _list(f.get("Source", "")), _list(f.get("Checks", "")), f.get("Statement", ""))
        for i, t, f, _ in _blocks(sections.get("Security constraints", "")))
    rules = {}
    for row in _table(sections.get("Data rules", "")):
        if len(row) >= 2 and row[0].startswith("`"):
            rules[row[0].strip("`")] = row[1]
    contracts = _fields(sections.get("Contracts", "").splitlines())
    codes, statuses, mode = [], [], None
    for line in sections.get("Behavior", "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else None
        if cells is None:
            mode = None
        elif cells[0] in ("Code", "Status"):
            mode = codes if cells[0] == "Code" else statuses
        elif mode is not None and cells[0].startswith("`"):
            mode.append(cells[0].strip("`"))
    return Spec(path, header, sections, criteria, constraints, rules, contracts.get("Contract"),
                _list(contracts.get("Outbound", "")), tuple(codes), tuple(statuses))


def load_tasks(path: Path) -> TaskList:
    """A task list from a tasks.md file, or from the tasks.md in a spec folder."""
    path = Path(path)
    path = path / "tasks.md" if path.is_dir() else path
    text = path.read_text(encoding="utf-8")
    head, _ = text.split("\n### ", 1) if "\n### " in text else (text, "")
    tasks = tuple(
        Task(i, t, _list(f.get("Checks", "")), _list(f.get("Depends on", "")), _list(f.get("Files", "")),
             f.get("Risk", ""), f.get("Sensitive", ""), f.get("Untrusted input", ""), f.get("Tier", ""),
             f.get("Why", ""))
        for i, t, f, _ in _blocks(text))
    return TaskList(path, _fields(head.splitlines()).get("Spec", ""), tasks)


def load_contract(spec: Spec) -> Contract | None:
    """The contract the spec names, or None if it is missing or not valid JSON."""
    if not spec.contract_path:
        return None
    path = spec.path.parent / spec.contract_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    defs = {name: d.get("properties", {}) for name, d in data.get("$defs", {}).items()}
    return Contract(path, str(data.get("x-spec-version", "")), defs)


def load_prd(path: Path) -> Prd:
    """Requirement IDs and criteria from a PRD in Lab 4.1's format."""
    text = Path(path).read_text(encoding="utf-8")
    version = re.search(r"^Version: (\S+)$", text, re.M)
    requirements, criteria, current = [], {}, None
    body = text.split("\n## Requirements", 1)[-1]
    for line in body.splitlines():
        m = re.match(r"^### (ESC-[RN]\d+) — ", line)
        if m:
            current = m.group(1)
            requirements.append(current)
            continue
        m = re.match(r"^- (ESC-AC\d+): (.*)$", line)
        if m and current:
            criteria[m.group(1)] = (current, m.group(2).strip())
    return Prd(version.group(1) if version else "", tuple(requirements), criteria)
