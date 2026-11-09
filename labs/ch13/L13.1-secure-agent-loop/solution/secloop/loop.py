"""The agent loop's gates, replayed over the 160 changes (provided; uses TODOs 1, 2 and 3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import AS_OF, DATA, gate_policy, load_json, load_jsonl, mirror_policy
from .deps import check_requirements
from .fixes import accepted_by, verify_fix
from .gates import BLOCKED, decide
from .sarif import load_sarif

SCANNERS = ("semgrep", "gitleaks", "trivy")
REASON_KINDS = ("rescan still finds", "tests fail", "adds marker", "changes protected path",
                "changes a file outside")


def load_changes(data: Path = DATA) -> list[dict]:
    return load_jsonl(data / "changes" / "changes.jsonl")


def dependency_findings(change: dict, data: Path = DATA) -> list:
    req = change.get("requirements")
    if not req:
        return []
    return check_requirements(change["id"], req["file"], req["added_lines"], mirror_policy(),
                              load_json(data / "packages" / "mirror-index.json"),
                              load_json(data / "packages" / "public-index.json"))


def run(data: Path = DATA, as_of: str = AS_OF, suppressions: list[dict] | None = None,
        reports: tuple[str, ...] = SCANNERS) -> dict[str, dict]:
    """Gate every change at pre-commit and in CI. Returns outcomes keyed by change ID."""
    policy = gate_policy()
    sups = load_json(data / "suppressions.json")["suppressions"] if suppressions is None else suppressions
    found: dict[str, list] = {}
    for s in reports:
        for f in load_sarif(data / "scans" / f"{s}.sarif.json"):
            found.setdefault(f.change, []).append(f)
    outcomes = {}
    day = date.fromisoformat(as_of)
    for ch in load_changes(data):
        findings = found.get(ch["id"], []) + dependency_findings(ch, data)
        res = {st: decide(findings, policy, sups, day, st, set(reports)) for st in ("pre-commit", "ci")}
        outcomes[ch["id"]] = {"pre-commit": res["pre-commit"].status, "ci": res["ci"].status, "results": res,
                              "blocking_scanners": {f.scanner for r in res.values() for f in r.blocking}}
    return outcomes


def fix_summary(data: Path = DATA) -> dict:
    """Each re-verification mode's acceptances, and how many bad fixes each would let through."""
    policy = gate_policy()
    changes = {c["id"]: c for c in load_changes(data)}
    fixes = load_jsonl(data / "fixes" / "fixes.jsonl")
    rows, reasons = {}, {}
    for f in fixes:
        own = [x["path"] for x in changes[f["change"]]["files"]] or ["deploy/requirements.txt"]
        why = verify_fix(f, own, policy)
        f["_policy_ok"] = not why
        for r in why:
            key = next(k for k in REASON_KINDS if r.startswith(k))
            reasons[key] = reasons.get(key, 0) + 1
    good = sum(f["_policy_ok"] for f in fixes)
    for mode in ("claim", "rescan", "rescan+tests"):
        acc = [f for f in fixes if accepted_by(f, mode)]
        rows[mode] = (len(acc), sum(not f["_policy_ok"] for f in acc))
    rows["full policy"] = (good, 0)
    kinds = {}
    for f in fixes:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    return {"attempts": len(fixes), "modes": rows, "kinds": kinds, "reasons": dict(sorted(reasons.items()))}


def blocked(outcome: dict) -> bool:
    return outcome["pre-commit"] == BLOCKED or outcome["ci"] == BLOCKED
