"""Findings, the check catalogue and the lexicon (provided; no TODOs here)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SEVERITIES = ("critical", "high", "medium", "low")

# code: (severity, area, title). Severities are fixed so that two people
# checking the same PRD always get the same counts.
CHECKS: dict[str, tuple[str, str, str]] = {
    "RQ001": ("high", "provenance", "Requirement or goal has no source"),
    "RQ002": ("high", "provenance", "Source document does not exist"),
    "RQ003": ("high", "provenance", "Quote does not appear verbatim in its source"),
    "RQ004": ("medium", "provenance", "Quote too short to establish provenance"),
    "RQ010": ("medium", "clarity", "Vague term"),
    "RQ011": ("medium", "testability", "Weak modal verb where an obligation is meant"),
    "RQ012": ("high", "testability", "Non-functional requirement has no measurable threshold"),
    "RQ020": ("high", "criteria", "Requirement has no acceptance criteria"),
    "RQ021": ("medium", "criteria", "Criterion is not in Given/When/Then form"),
    "RQ030": ("high", "consistency", "Two requirements set the same value differently"),
    "RQ040": ("medium", "dependencies", "Uses a concept Relay lacks that no requirement introduces"),
    "RQ041": ("low", "dependencies", "Uses a concept introduced elsewhere without depending on it"),
    "RQ050": ("high", "coverage", "Required non-functional category not covered"),
    "RQ060": ("medium", "traceability", "Goal has no requirement"),
    "RQ061": ("medium", "traceability", "Requirement has no known goal"),
    "RQ062": ("high", "traceability", "Goal lacks a measure, baseline or target"),
    "RQ063": ("medium", "traceability", "Requirement cites a decision that is not recorded"),
    "RQ064": ("high", "traceability", "Identifier used more than once"),
    "RQ065": ("medium", "traceability", "Requirement depends on an unknown requirement"),
    "RQ071": ("critical", "security", "Quote comes from instruction-like text in a source"),
    "RQ080": ("high", "approval", "Not approved by the named product owner"),
}

# The gate policy (Chapter 4, worked example 2). Blocking checks give an exact
# answer from the PRD text: a quote is in its source or not, a link resolves or
# not, two declared values differ or not. Warnings depend on word lists whose
# held-out recall Lab 4.2 measured at 43% (vague terms) and 50% (untestable
# wording), with precision intervals too wide to justify blocking a merge.
BLOCKING = frozenset({
    "RQ001", "RQ002", "RQ003", "RQ004",            # provenance
    "RQ020", "RQ021",                              # criteria present, in Given/When/Then form
    "RQ030",                                       # declared values that differ
    "RQ050",                                       # NFR categories covered
    "RQ060", "RQ061", "RQ062", "RQ063", "RQ064", "RQ065",  # traceability
    "RQ071",                                       # quote from flagged source text
    "RQ080",                                       # approval record complete
})
WARNING = frozenset(CHECKS) - BLOCKING             # RQ010-RQ012, RQ040-RQ041: word lists

AREAS = ("provenance", "clarity", "testability", "criteria", "consistency", "dependencies",
         "coverage", "traceability", "security", "approval")


@dataclass(frozen=True)
class Finding:
    code: str
    item: str      # the requirement, goal, criterion or "PRD" the finding is about
    message: str

    @property
    def severity(self) -> str:
        return CHECKS[self.code][0]

    @property
    def area(self) -> str:
        return CHECKS[self.code][1]

    def line(self) -> str:
        return f"{self.code} [{self.severity}] {self.item}: {self.message}"


def finding(code: str, item: str, message: str) -> Finding:
    if code not in CHECKS:
        raise KeyError(f"unknown check {code}")
    return Finding(code, item, message)


@dataclass(frozen=True)
class Lexicon:
    version: str
    min_quote_words: int
    vague_terms: tuple[str, ...]
    weak_modals: tuple[str, ...]
    measurable_patterns: tuple[str, ...]
    required_nfr_categories: tuple[str, ...]
    concepts: dict[str, tuple[str, ...]]
    injection_patterns: tuple[str, ...]


def load_lexicon(path: Path) -> Lexicon:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Lexicon(
        version=raw["lexicon_version"],
        min_quote_words=raw["min_quote_words"],
        vague_terms=tuple(raw["vague_terms"]),
        weak_modals=tuple(raw["weak_modals"]),
        measurable_patterns=tuple(raw["measurable_patterns"]),
        required_nfr_categories=tuple(raw["required_nfr_categories"]),
        concepts={k: tuple(v) for k, v in raw["concepts"].items()},
        injection_patterns=tuple(raw["injection_patterns"]),
    )
