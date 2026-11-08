"""Checks for decision records and threat models.

TODO 4 (check_adr) and TODO 5 (check_threat_model) are yours in starter/.
Every finding blocks the gate. Like Lab 4.1's RQ080, ADR009 checks the
decision *record*: anyone can type a name. The decision itself is the named
architect's required review on the pull request that adds the ADR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .docs import ADR, ThreatModel
from .model import Catalogue, Option

CATALOGUE = {
    "ADR001": "Required header field missing (Status, Date, Decided by, Links, Revisit when)",
    "ADR002": "Status is not one of proposed, accepted, superseded, deprecated, rejected",
    "ADR003": "Required section missing (Context, Options considered, Decision, Consequences, Rejected alternatives)",
    "ADR004": "Fewer than two options considered",
    "ADR005": "An option considered is neither the decision nor a rejected alternative",
    "ADR006": "Rejected alternative without a reason of at least 8 words",
    "ADR007": "Link to an ID that is not in the driver catalogue or the PRD's decisions",
    "ADR008": "No link to any PRD decision (D1-D9) or NFR (ESC-N01-N10)",
    "ADR009": "Decided by is not a named person on the team",
    "ADR010": "Superseded without Superseded by",
    "ADR011": "Rejected alternative without a Revisit if condition",
    "TM001": "Trust boundary with no threat",
    "TM002": "Threat on a boundary the option does not have",
    "TM003": "STRIDE category not one of S, T, R, I, D, E",
    "TM004": "Threat without a control",
    "TM005": "Control without evidence (a test, a check, a planned test, or a named residual-risk owner)",
    "TM006": "Diagram missing, or does not label every trust boundary",
    "TM007": "No reviewer, or the reviewer is the author",
}

STATUSES = {"proposed", "accepted", "superseded", "deprecated", "rejected"}
REQUIRED_FIELDS = ("Status", "Date", "Decided by", "Links", "Revisit when")
REQUIRED_SECTIONS = ("Context", "Options considered", "Decision", "Consequences", "Rejected alternatives")
PRD_ID = re.compile(r"^(D[1-9]|ESC-N(0[1-9]|10))$")
MIN_REASON_WORDS = 8
STRIDE = set("STRIDE")


@dataclass(frozen=True)
class Finding:
    code: str
    item: str
    message: str


def check_adr(adr: ADR, catalogue: Catalogue) -> list[Finding]:
    """TODO 4. Check one ADR against CATALOGUE codes ADR001-ADR011, in that order.

    - ADR001: one finding per missing or empty REQUIRED_FIELDS entry, in field order.
    - ADR002: Status present but not in STATUSES (compare in lower case).
    - ADR003: one finding per missing REQUIRED_SECTIONS entry, in section order.
    - ADR004: fewer than two options under "Options considered".
    - ADR005: an option letter that is not named as "Option X" in the Decision section
      and is not under "Rejected alternatives" (one finding per letter, in order).
    - ADR006: a rejected alternative whose reason has fewer than MIN_REASON_WORDS words
      (one per letter, in order of appearance).
    - ADR007: one finding per link not in catalogue.known_ids(), in link order.
    - ADR008: no link matches PRD_ID (whether or not it is known).
    - ADR009: "Decided by" present but its first word (before any space or "(") is not in
      catalogue.people.
    - ADR010: status "superseded" and no "Superseded by" field.
    - ADR011: a rejected alternative with no non-empty "Revisit if:" line (adr.revisit has
      the letter mapped to "" or no entry), one per letter in order of appearance.
    The finding's `item` is the ADR's title up to the first " — " (for example "ADR-007").
    """
    item = adr.title.split(" — ")[0]
    out: list[Finding] = []
    for name in REQUIRED_FIELDS:
        if not adr.fields.get(name):
            out.append(Finding("ADR001", item, f"missing field {name!r}"))
    status = adr.fields.get("Status", "").lower()
    if status and status not in STATUSES:
        out.append(Finding("ADR002", item, f"status {status!r}"))
    for name in REQUIRED_SECTIONS:
        if name not in adr.sections:
            out.append(Finding("ADR003", item, f"missing section {name!r}"))
    if len(adr.options) < 2:
        out.append(Finding("ADR004", item, f"{len(adr.options)} option(s) considered"))
    decision = adr.sections.get("Decision", "")
    for letter in adr.options:
        if f"Option {letter}" not in decision and letter not in adr.rejected:
            out.append(Finding("ADR005", item, f"Option {letter} is neither chosen nor rejected"))
    for letter, reason in adr.rejected.items():
        if len(reason.split()) < MIN_REASON_WORDS:
            out.append(Finding("ADR006", item, f"Option {letter}: reason {reason!r} has {len(reason.split())} words"))
    known = catalogue.known_ids()
    for link in adr.links:
        if link not in known:
            out.append(Finding("ADR007", item, f"unknown ID {link!r}"))
    if not any(PRD_ID.match(link) for link in adr.links):
        out.append(Finding("ADR008", item, "no link to a PRD decision or NFR"))
    decider = adr.fields.get("Decided by", "")
    if decider:
        name = re.split(r"[ (]", decider, maxsplit=1)[0]
        if name not in catalogue.people:
            out.append(Finding("ADR009", item, f"decided by {name!r}, not a named person on the team"))
    if status == "superseded" and not adr.fields.get("Superseded by"):
        out.append(Finding("ADR010", item, "superseded, but by what?"))
    for letter in adr.rejected:
        if not adr.revisit.get(letter):
            out.append(Finding("ADR011", item, f"Option {letter}: no 'Revisit if' condition"))
    return out


def check_threat_model(tm: ThreatModel, option: Option) -> list[Finding]:
    """TODO 5. Check one threat model against its option, codes TM001-TM007, in that order.

    - TM001: one finding per boundary ID in option.boundaries (sorted) with no threat row.
    - TM002: a threat row whose Boundary is neither an ID in option.boundaries nor "none"
      ("none" marks a threat inside one trust zone).
    - TM003: a row whose STRIDE cell, split on "/" or ",", has any part (stripped) that is
      not one of S, T, R, I, D, E, or is empty.
    - TM004: a row with an empty Control.
    - TM005: a row with a Control but an empty Evidence.
    - TM006: the diagram is empty, or one finding per boundary ID (sorted) whose text does
      not appear in the diagram. Report one finding with message "no diagram" if empty.
    - TM007: "Reviewed by" empty, or equal to "Author".
    Rows are checked in order; TM002-TM005 use the row's number as part of the message.
    The finding's `item` is f"TM-{option.id}".
    """
    item = f"TM-{option.id}"
    out: list[Finding] = []
    covered = {t.boundary for t in tm.threats}
    for b in sorted(option.boundaries):
        if b not in covered:
            out.append(Finding("TM001", item, f"boundary {b} ({option.boundaries[b]}) has no threat"))
    for t in tm.threats:
        if t.boundary not in option.boundaries and t.boundary != "none":
            out.append(Finding("TM002", item, f"threat {t.number}: unknown boundary {t.boundary!r}"))
    for t in tm.threats:
        parts = [p.strip() for p in re.split(r"[/,]", t.stride)]
        if not parts or any(p not in STRIDE or len(p) != 1 for p in parts):
            out.append(Finding("TM003", item, f"threat {t.number}: STRIDE {t.stride!r}"))
    for t in tm.threats:
        if not t.control:
            out.append(Finding("TM004", item, f"threat {t.number}: no control"))
    for t in tm.threats:
        if t.control and not t.evidence:
            out.append(Finding("TM005", item, f"threat {t.number}: control without evidence"))
    if not tm.diagram.strip():
        out.append(Finding("TM006", item, "no diagram"))
    else:
        for b in sorted(option.boundaries):
            if b not in tm.diagram:
                out.append(Finding("TM006", item, f"diagram does not label {b}"))
    reviewer, author = tm.fields.get("Reviewed by", ""), tm.fields.get("Author", "")
    if not reviewer or reviewer == author:
        out.append(Finding("TM007", item, "no independent reviewer"))
    return out
