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
    """TODO 4. Check one ADR against CATALOGUE codes ADR001-ADR010, in that order.

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
    The finding's `item` is the ADR's title up to the first " — " (for example "ADR-007").
    """
    raise NotImplementedError("TODO 4: check_adr")


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
    raise NotImplementedError("TODO 5: check_threat_model")
