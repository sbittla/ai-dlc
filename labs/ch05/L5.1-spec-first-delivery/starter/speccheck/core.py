"""Findings and the spec checker's catalogue of checks.

A finding is a question for a person, not an edit for an agent. The gate
(`report --gate`) blocks a merge on every check except the three warnings,
whose answers depend on judgement: a thin section, a test for a criterion this
spec does not cover, and a task that may be too large.
"""

from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("critical", "high", "medium", "low")

# code: (severity, area, title)
CHECKS: dict[str, tuple[str, str, str]] = {
    "SP001": ("high", "structure", "Required header field missing"),
    "SP002": ("high", "structure", "Version is not MAJOR.MINOR.PATCH"),
    "SP010": ("high", "structure", "Required section missing"),
    "SP011": ("medium", "structure", "Required section is empty or still marked TO COMPLETE"),
    "SP020": ("high", "criteria", "Criterion is not in the PRD"),
    "SP021": ("high", "criteria", "Criterion text differs from the PRD"),
    "SP022": ("high", "criteria", "Criterion's requirement differs from the PRD"),
    "SP023": ("high", "criteria", "Coverage is not full or partial, or a partial criterion names nothing deferred"),
    "SP030": ("high", "tests", "Criterion has no test with its ID"),
    "SP031": ("medium", "tests", "Test is named after a criterion this spec does not include"),
    "SP032": ("high", "tests", "Security constraint names a policy test that does not exist"),
    "SP040": ("high", "tasks", "Task checks no criterion or security constraint"),
    "SP041": ("high", "tasks", "Task checks an ID this spec does not define"),
    "SP042": ("high", "tasks", "Criterion or security constraint is covered by no task"),
    "SP043": ("high", "tasks", "Task depends on an unknown task, or dependencies form a cycle"),
    "SP044": ("medium", "tasks", "Task may be too large (more than 4 checks or 3 files)"),
    "SP045": ("high", "tasks", "Risk, sensitivity or untrusted-input label missing or invalid"),
    "SP050": ("high", "tiers", "Autonomy tier missing or not T0-T4"),
    "SP051": ("critical", "tiers", "Task reads untrusted input at a tier above T2"),
    "SP052": ("high", "tiers", "Sensitive task at T4"),
    "SP060": ("high", "data", "Data rules missing, or a contract field has no classification"),
    "SP061": ("high", "data", "Unknown data classification"),
    "SP062": ("critical", "data", "Outbound document carries a Confidential or Restricted field"),
    "SP070": ("high", "contract", "Contract missing or unreadable"),
    "SP071": ("high", "contract", "Contract version differs from the spec version"),
    "SP072": ("high", "security", "Security constraint has no source or no check"),
    "SP080": ("high", "approval", "Approval record incomplete"),
    "SP081": ("high", "trace", "Spec is derived from a different PRD version"),
    "SP082": ("high", "trace", "Task list is for a different spec or spec version"),
}

WARNING = {"SP011", "SP031", "SP044"}
BLOCKING = set(CHECKS) - WARNING

REQUIRED_HEADER = ("Spec", "Version", "Status", "Derived from", "Risk", "Product owner", "Tech lead",
                   "Approved by", "Approved on")
REQUIRED_SECTIONS = ("Goals", "Non-goals", "Actors", "Behavior", "Non-functional requirements", "Contracts",
                     "Data rules", "Security constraints", "Acceptance criteria")
CLASSIFICATIONS = ("Public", "Internal", "Confidential", "Restricted")
TIERS = ("T0", "T1", "T2", "T3", "T4")
RISKS = ("low", "medium", "high")
UNTRUSTED_CAP = "T2"  # Chapter 1: an agent that reads and acts on untrusted input is capped at T2
MAX_TASK_CHECKS = 4
MAX_TASK_FILES = 3


@dataclass(frozen=True)
class Finding:
    code: str
    item: str  # the spec, section, criterion, task or field the finding is about
    message: str

    @property
    def severity(self) -> str:
        return CHECKS[self.code][0]

    @property
    def area(self) -> str:
        return CHECKS[self.code][1]

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING


def finding(code: str, item: str, message: str) -> Finding:
    if code not in CHECKS:
        raise KeyError(code)
    return Finding(code, item, message)
