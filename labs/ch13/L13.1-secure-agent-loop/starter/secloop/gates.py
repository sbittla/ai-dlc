"""The gate decision under relay-security-gates-v1 (TODO 1 in starter/)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .sarif import Finding

PASS, BLOCKED, CANNOT_CHECK = 0, 1, 2


@dataclass
class GateResult:
    status: int
    blocking: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    suppressed: list[tuple[Finding, str]] = field(default_factory=list)      # (finding, suppression id)
    ignored_suppressions: list[tuple[str, str]] = field(default_factory=list)  # (suppression id, why)
    missing: list[str] = field(default_factory=list)                          # scanner reports absent


def suppression_problem(sup: dict, policy: dict, as_of: date) -> str | None:
    """Why a suppression may not be applied, or None if it is valid."""
    raise NotImplementedError("TODO 1: why a suppression may not be applied")


def decide(findings: list[Finding], policy: dict, suppressions: list[dict], as_of: date, stage: str,
           reports_present: set[str]) -> GateResult:
    """Decide one change at one stage.

    - Only findings from the stage's scanners count (policy["stages"][stage]["scanners"]).
    - If any of the stage's scanners other than depgate has no report in `reports_present`, the status is
      CANNOT_CHECK (2) and `missing` lists them, sorted; findings are still classified.
    - A suppression applies to a finding when its rule and fingerprint both match, the finding's scanner is
      not in never_suppressible, and suppression_problem() returns None. A suppression that matches a
      finding but is invalid is listed once in ignored_suppressions with its reason, and the finding counts
      as if unsuppressed.
    - A finding that is not suppressed blocks if its scanner is in always_block or its severity is at least
      block_at_or_above; otherwise it is a warning.
    - Status: CANNOT_CHECK if a report is missing, else BLOCKED if anything blocks, else PASS.
    """
    raise NotImplementedError("TODO 1: decide one change at one stage")
