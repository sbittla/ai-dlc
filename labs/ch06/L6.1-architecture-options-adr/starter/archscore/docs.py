"""Parse ADRs and threat models written in this lab's Markdown formats (provided).

ADR format (templates/adr.md):

    # ADR-007 — Title
    Status: accepted                 header fields, one per line, before the first "##"
    Date: 2026-11-25
    Decided by: sam.o
    Links: D3, ESC-N01, CON-4        comma-separated IDs
    Revisit when: ...

    ## Context                       sections, by "## " heading
    ## Options considered
    ### Option A — Name              each option considered is a "### Option X — name" heading
    ## Decision                      names the chosen option as "Option X"
    ## Consequences
    ## Rejected alternatives
    ### Option B — Name              one per rejected option, with a line
    Rejected because: ...            "Rejected because: <reason>"
    Revisit if: ...                  and "Revisit if: <the change that would reopen it>"

Threat-model format (templates/threat-model.md): header fields (Option, Author,
Reviewed by, Date), a "## Diagram" section with a Mermaid block, and a
"## Threats" table with columns #, Boundary, STRIDE, Threat, Control, Evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADING = re.compile(r"^(#{1,3}) (.+?)\s*$")
FIELD = re.compile(r"^([A-Z][A-Za-z ]+):\s*(.*)$")
OPTION = re.compile(r"^Option ([A-Z])\b")


@dataclass
class ADR:
    path: str
    title: str
    fields: dict[str, str]
    sections: dict[str, str]                         # "## " heading -> body text
    options: list[str]                               # option letters under "Options considered"
    rejected: dict[str, str] = field(default_factory=dict)   # option letter -> reason ("" if missing)
    revisit: dict[str, str] = field(default_factory=dict)    # option letter -> revisit condition

    @property
    def links(self) -> list[str]:
        return [x.strip() for x in self.fields.get("Links", "").split(",") if x.strip()]


def parse_adr(text: str, path: str = "<text>") -> ADR:
    title, fields, sections = "", {}, {}
    options, rejected, revisit = [], {}, {}
    current, sub = None, None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            level, name = len(m[1]), m[2]
            if level == 1:
                title = name
            elif level == 2:
                current, sub = name, None
                sections.setdefault(name, "")
            else:
                om = OPTION.match(name)
                sub = om[1] if om else None
                if current == "Options considered" and sub:
                    options.append(sub)
                elif current == "Rejected alternatives" and sub:
                    rejected.setdefault(sub, "")
            continue
        if current is None:
            fm = FIELD.match(line)
            if fm:
                fields[fm[1]] = fm[2].strip()
            continue
        sections[current] += line + "\n"
        if current == "Rejected alternatives" and sub and line.startswith("Rejected because:"):
            rejected[sub] = line.split(":", 1)[1].strip()
        if current == "Rejected alternatives" and sub and line.startswith("Revisit if:"):
            revisit[sub] = line.split(":", 1)[1].strip()
    return ADR(path, title, fields, sections, options, rejected, revisit)


def load_adr(path: str | Path) -> ADR:
    return parse_adr(Path(path).read_text(encoding="utf-8"), str(path))


@dataclass(frozen=True)
class Threat:
    number: str
    boundary: str
    stride: str
    threat: str
    control: str
    evidence: str


@dataclass
class ThreatModel:
    path: str
    fields: dict[str, str]
    diagram: str          # the Mermaid source under "## Diagram" ("" if none)
    threats: list[Threat]


def parse_threat_model(text: str, path: str = "<text>") -> ThreatModel:
    fields, diagram, threats = {}, [], []
    section, in_code = None, False
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and not in_code:
            section = m[2] if len(m[1]) == 2 else section
            continue
        if section is None:
            fm = FIELD.match(line)
            if fm:
                fields[fm[1]] = fm[2].strip()
        elif section == "Diagram":
            if line.startswith("```"):
                in_code = not in_code
            elif in_code:
                diagram.append(line)
        elif section == "Threats" and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 6 and cells[0] not in ("#", "---:", "---") and not set(cells[0]) <= set("-:"):
                threats.append(Threat(*cells))
    return ThreatModel(path, fields, "\n".join(diagram), threats)


def load_threat_model(path: str | Path) -> ThreatModel:
    return parse_threat_model(Path(path).read_text(encoding="utf-8"), str(path))
