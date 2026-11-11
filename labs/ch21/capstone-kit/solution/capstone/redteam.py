"""The red-team exchange log and its validator (TODO 4 in starter/).

One team attacks another team's sandboxed deployment, inside a written scope and an agreed window, and logs each
finding with the shared template. The log records what was attacked and how to reproduce it by reference to
the attack-class catalogue and a placeholder variant ID. It never holds attack text: the variants themselves
stay in the course repository under the ethics agreement, and the log's schema has no field for them.

Rules (all from Chapter 21, Section 21.3):

    RT001  the target is not in the written scope
    RT002  the finding is timed outside the agreed window
    RT003  a template field is missing or empty
    RT004  the severity is not on the shared scale
    RT005  a critical or high finding is neither fixed and re-tested, nor formally blocked with an owner, a date
           and a reviewer who is not on the defending team
    RT006  a field the template does not have (it could carry attack text)
    RT007  a finding marked fixed has no pull request or no re-test that blocked it
    RT008  the attacking team is the defending team
    RT009  a finding ID is used twice
"""

from __future__ import annotations

from datetime import datetime

from . import Finding

SCALE = ("critical", "high", "medium", "low")
TEMPLATE = ("target", "at", "class", "variant", "severity", "attacked", "steps", "evidence", "impact",
            "suggested_fix", "status")
ALLOWED = set(TEMPLATE) | {"id", "fix", "block", "detection"}
STATUSES = ("open", "fixed", "blocked", "not reproduced")


def retested(finding: dict) -> bool:
    fix = finding.get("fix") or {}
    return bool(fix.get("pr")) and fix.get("retest_result") == "blocked"


def closed(finding: dict, defenders: set[str]) -> bool:
    """Is a critical or high finding closed before the readiness review? Either it is "fixed" with a pull
    request and a re-test that the attack class's variant now fails against (fix.retest_result "blocked"), or it
    is "blocked" formally: block.owner, block.due and block.reviewer all present, and the reviewer is not one of
    the defending team's members (`defenders`), who cannot accept their own risk."""
    if finding.get("status") == "fixed":
        return retested(finding)
    block = finding.get("block") or {}
    return (finding.get("status") == "blocked" and bool(block.get("owner")) and bool(block.get("due"))
            and bool(block.get("reviewer")) and block["reviewer"] not in defenders)


def _time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def validate(log: dict) -> dict:
    """Check a log. Returns {"findings": [Finding], "valid": [ids], "defender_credit": n, "attacker_credit": n,
    "open_high": [ids]}. A finding is valid when it has no RT001-RT004, RT006 or RT009 problem. The defending team
    earns one credit per fix re-tested as blocked and one per finding whose detection fired; the attacking team
    one per valid finding."""
    out: list[Finding] = []
    scope = log.get("scope", {})
    targets = set(scope.get("targets", []))
    start, end = _time(scope["window"]["start"]), _time(scope["window"]["end"])
    defenders = set(log.get("defender_members", []))
    if log.get("attacker") == log.get("defender"):
        out.append(Finding("RT008", "block", "log", f"{log.get('attacker')} attacked its own system"))
    seen: set[str] = set()
    valid, open_high = [], []
    defender_credit = 0
    for f in log.get("findings", []):
        fid = f.get("id", "?")
        problems = []
        if fid in seen:
            problems.append(Finding("RT009", "block", fid, "finding ID used twice"))
        seen.add(fid)
        extra = sorted(set(f) - ALLOWED)
        if extra:
            problems.append(Finding("RT006", "block", fid, f"field(s) {', '.join(extra)} are not in the template"))
        missing = [k for k in TEMPLATE if not f.get(k)]
        if missing:
            problems.append(Finding("RT003", "block", fid, f"missing {', '.join(missing)}"))
        if f.get("target") and f["target"] not in targets:
            problems.append(Finding("RT001", "block", fid, f"target {f['target']!r} is outside the written scope"))
        if f.get("at") and not start <= _time(f["at"]) <= end:
            problems.append(Finding("RT002", "block", fid, f"{f['at']} is outside the agreed window"))
        if f.get("severity") and f["severity"] not in SCALE:
            problems.append(Finding("RT004", "block", fid, f"severity {f['severity']!r} is not on the shared scale"))
        status = f.get("status")
        if status == "fixed" and not retested(f):
            problems.append(Finding("RT007", "block", fid, "marked fixed without a pull request and a re-test "
                                                          "that blocked it"))
        if f.get("severity") in ("critical", "high"):
            if not closed(f, defenders):
                problems.append(Finding("RT005", "block", fid, f"{f['severity']} finding is {status}: fix it and "
                                                              "re-test, or block it formally"))
                open_high.append(fid)
        out += problems
        if not any(p.code in ("RT001", "RT002", "RT003", "RT004", "RT006", "RT009") for p in problems):
            valid.append(fid)
            if status == "fixed" and retested(f):
                defender_credit += 1
            if (f.get("detection") or {}).get("fired"):
                defender_credit += 1
    return {"findings": out, "valid": valid, "defender_credit": defender_credit, "attacker_credit": len(valid),
            "open_high": open_high}
