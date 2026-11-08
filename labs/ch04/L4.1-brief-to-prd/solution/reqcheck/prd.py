"""Parse a PRD written in the lab's Markdown format (provided; no TODOs here).

The format, in full (see templates/prd.md):

    # PRD — <feature>
    Version: 1.0
    Status: draft | approved
    Product owner: <name>
    Approved by: <name>
    Approved on: <YYYY-MM-DD>

    ## Goals
    ### G1 — <title>
    Measure: / Baseline: / Target: / Source: <DOC-ID> | <verbatim quote>

    ## Decisions
    ### D1 — <title>
    Resolves: / Decision: / Decided by:

    ## Requirements
    ### ESC-R01 — <title>
    Kind: functional | nfr
    Category: <nfr category>            (nfr only)
    Goal: G1, G2
    Decision: D1
    Source: <DOC-ID> | <verbatim quote>  (repeat the line for several sources)
    Statement: <one paragraph>
    Value: <key> = <value>               (optional; repeatable)
    Introduces: <concept>                (optional)
    Depends on: ESC-R01, ESC-R02         (optional)
    Criteria:
    - ESC-AC01: Given ..., when ..., then ...

Other sections (Problem, Users, Scope, Constraints, Risks, Open questions)
are free text for people; the checker does not parse them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^###\s+(?P<id>[A-Za-z0-9-]+)\s+—\s+(?P<title>.+?)\s*$")
FIELD = re.compile(r"^(?P<key>[A-Z][A-Za-z ]+?):\s*(?P<value>.*)$")
CRITERION = re.compile(r"^-\s+(?P<id>[A-Za-z0-9-]+):\s*(?P<text>.+?)\s*$")


@dataclass(frozen=True)
class SourceRef:
    doc: str
    quote: str


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str


@dataclass
class Goal:
    id: str
    title: str
    measure: str = ""
    baseline: str = ""
    target: str = ""
    sources: list[SourceRef] = field(default_factory=list)


@dataclass
class Decision:
    id: str
    title: str
    resolves: str = ""
    decision: str = ""
    decided_by: str = ""


@dataclass
class Requirement:
    id: str
    title: str
    kind: str = ""
    category: str = ""
    goals: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    statement: str = ""
    values: list[tuple[str, str]] = field(default_factory=list)
    introduces: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    criteria: list[Criterion] = field(default_factory=list)


@dataclass
class PRD:
    title: str = ""
    version: str = ""
    status: str = ""
    product_owner: str = ""
    approved_by: str = ""
    approved_on: str = ""
    goals: list[Goal] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)


def _ids(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _source(value: str) -> SourceRef:
    doc, sep, quote = value.partition("|")
    return SourceRef(doc.strip(), quote.strip() if sep else "")


def parse(text: str) -> PRD:
    prd = PRD()
    section = ""
    item = None
    in_criteria = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if line.startswith("# ") and not prd.title:
            prd.title = line[2:].strip()
            continue
        if line.startswith("## "):
            section, item, in_criteria = line[3:].strip().lower(), None, False
            continue
        m = HEADING.match(line)
        if m and section in ("goals", "decisions", "requirements"):
            cls = {"goals": Goal, "decisions": Decision, "requirements": Requirement}[section]
            item = cls(m["id"], m["title"])
            {"goals": prd.goals, "decisions": prd.decisions, "requirements": prd.requirements}[section].append(item)
            in_criteria = False
            continue
        if in_criteria and isinstance(item, Requirement):
            c = CRITERION.match(line)
            if c:
                item.criteria.append(Criterion(c["id"], c["text"]))
                continue
            if line.strip():
                in_criteria = False
        f = FIELD.match(line)
        if not f:
            continue
        key, value = f["key"].strip().lower(), f["value"].strip()
        if item is None:
            if section == "":
                attr = {"version": "version", "status": "status", "product owner": "product_owner",
                        "approved by": "approved_by", "approved on": "approved_on"}.get(key)
                if attr:
                    setattr(prd, attr, value)
            continue
        if isinstance(item, Goal):
            if key in ("measure", "baseline", "target"):
                setattr(item, key, value)
            elif key == "source":
                item.sources.append(_source(value))
        elif isinstance(item, Decision):
            attr = {"resolves": "resolves", "decision": "decision", "decided by": "decided_by"}.get(key)
            if attr:
                setattr(item, attr, value)
        else:
            if key == "kind":
                item.kind = value.lower()
            elif key == "category":
                item.category = value.lower()
            elif key == "goal":
                item.goals += _ids(value)
            elif key == "decision":
                item.decisions += _ids(value)
            elif key == "source":
                item.sources.append(_source(value))
            elif key == "statement":
                item.statement = value
            elif key == "value":
                k, _, v = value.partition("=")
                item.values.append((k.strip(), v.strip()))
            elif key == "introduces":
                item.introduces += _ids(value)
            elif key == "depends on":
                item.depends_on += _ids(value)
            elif key == "criteria":
                in_criteria = True
    return prd


def load(path: Path) -> PRD:
    return parse(path.read_text(encoding="utf-8"))
