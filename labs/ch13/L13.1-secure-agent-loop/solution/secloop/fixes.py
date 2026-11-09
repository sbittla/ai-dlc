"""Re-verifying a fix before it is accepted (TODO 3 in starter/)."""

from __future__ import annotations


def verify_fix(fix: dict, original_files: list[str], policy: dict) -> list[str]:
    """Reasons to refuse a fix; an empty list means accept it.

    `fix` is a record from data/fixes/fixes.jsonl; `original_files` the paths the original change touched
    (["deploy/requirements.txt"] for a dependency change); `policy` is security/gates.json. Check, in order,
    and give one reason per problem:

    1. "rescan still finds N" when fix["rescan_findings"] > 0.
    2. "tests fail" when not fix["tests_pass"].
    3. "adds marker <m>" for each forbidden marker (policy["fixes"]["forbidden_markers"]) that appears in
       any of fix["added_lines"], in the policy's order.
    4. "changes protected path <p>" for each changed file that starts with a protected path, in file order.
    5. "changes a file outside the change: <p>" for each other changed file not in original_files.
    The agent's claim ("fixed") is never evidence.
    """
    reasons = []
    if fix["rescan_findings"] > 0:
        reasons.append(f"rescan still finds {fix['rescan_findings']}")
    if not fix["tests_pass"]:
        reasons.append("tests fail")
    for marker in policy["fixes"]["forbidden_markers"]:
        if any(marker in line for line in fix["added_lines"]):
            reasons.append(f"adds marker {marker}")
    protected = policy["fixes"]["protected_paths"]
    for path in fix["files_changed"]:
        if any(path.startswith(p) for p in protected):
            reasons.append(f"changes protected path {path}")
        elif path not in original_files:
            reasons.append(f"changes a file outside the change: {path}")
    return reasons


def accepted_by(fix: dict, mode: str) -> bool:
    """What weaker re-verification modes would accept (provided, for comparison).

    claim: trust the agent's claim; rescan: the scanners find nothing; rescan+tests: and the tests pass.
    """
    if mode == "claim":
        return fix["claim"] == "fixed"
    if mode == "rescan":
        return fix["rescan_findings"] == 0
    if mode == "rescan+tests":
        return fix["rescan_findings"] == 0 and fix["tests_pass"]
    raise ValueError(mode)
