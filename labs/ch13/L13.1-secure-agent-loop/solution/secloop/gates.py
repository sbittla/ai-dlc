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
    rules = policy["suppressions"]
    if not sup.get("reason", "").strip():
        return "no reason"
    if sup.get("reviewed_by") not in rules["reviewers"]:
        return f"reviewer {sup.get('reviewed_by')!r} is not a person on the policy's list"
    if sup["reviewed_by"] == sup.get("author"):
        return "reviewed by its own author"
    created, expires = date.fromisoformat(sup["created"]), date.fromisoformat(sup["expires"])
    if expires < as_of:
        return f"expired on {sup['expires']}"
    if expires - created > timedelta(days=rules["max_days"]):
        return f"longer than {rules['max_days']} days"
    return None


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
    scanners = set(policy["stages"][stage]["scanners"])
    result = GateResult(PASS)
    result.missing = sorted(s for s in scanners - {"depgate"} if s not in reports_present)
    by_key = {}
    for sup in suppressions:
        by_key.setdefault((sup["rule"], sup["fingerprint"]), []).append(sup)
    for f in findings:
        if f.scanner not in scanners:
            continue
        applied = None
        for sup in by_key.get((f.rule, f.fingerprint), []):
            problem = ("this scanner's findings cannot be suppressed"
                       if f.scanner in policy["suppressions"]["never_suppressible"]
                       else suppression_problem(sup, policy, as_of))
            if problem is None:
                applied = sup["id"]
                break
            if (sup["id"], problem) not in result.ignored_suppressions:
                result.ignored_suppressions.append((sup["id"], problem))
        if applied:
            result.suppressed.append((f, applied))
        elif f.scanner in policy["always_block"] or f.severity >= policy["block_at_or_above"]:
            result.blocking.append(f)
        else:
            result.warnings.append(f)
    if result.missing:
        result.status = CANNOT_CHECK
    elif result.blocking:
        result.status = BLOCKED
    return result
