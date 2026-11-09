"""Read scanner reports in SARIF 2.1.0 form into one Finding type (provided)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import load_json


@dataclass(frozen=True)
class Finding:
    scanner: str          # semgrep, gitleaks, trivy or depgate
    rule: str
    severity: float       # security-severity, 0.0-10.0
    change: str           # the agent change the finding belongs to
    path: str
    line: int
    fingerprint: str
    message: str


def load_sarif(path: Path) -> list[Finding]:
    """Every result of every run. The change ID is the first part of the artifact URI."""
    doc = load_json(path)
    out = []
    for run in doc["runs"]:
        scanner = run["tool"]["driver"]["name"]
        for r in run["results"]:
            loc = r["locations"][0]["physicalLocation"]
            change, _, rel = loc["artifactLocation"]["uri"].partition("/")
            props = r.get("properties", {})
            # A real tool may omit security-severity; fall back on the SARIF level (error 8.0, else 4.0).
            severity = float(props.get("security-severity", 8.0 if r.get("level") == "error" else 4.0))
            out.append(Finding(scanner, r["ruleId"], severity, props.get("change", change), rel,
                               loc.get("region", {}).get("startLine", 0),
                               r.get("partialFingerprints", {}).get("primaryLocationLineHash", ""),
                               r["message"]["text"]))
    return out


def band(severity: float, policy: dict) -> str:
    """critical, high, medium, low or none, by the policy's bands (GitHub code scanning's convention)."""
    for floor, name in policy["bands"]:
        if severity >= floor:
            return name
    return "none"
