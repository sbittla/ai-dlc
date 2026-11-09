"""Optional live mode: run the real scanners on Relay 4.25.0 and gate their SARIF (provided; never run in tests).

    SECLOOP_LIVE=1 python -m secloop.live            # bash
    $env:SECLOOP_LIVE="1"; python -m secloop.live; Remove-Item Env:SECLOOP_LIVE   # PowerShell

It needs semgrep, gitleaks and trivy on PATH at versions you have reviewed; the lab installs none of them.
It runs them on the lab's own relay-repo/ copy only, offline where the tool allows (Semgrep with
--metrics=off and Relay's local rules; gitleaks on the directory; Trivy with --offline-scan, which needs
a vulnerability database already on disk). Cost: $0. A missing tool, a timeout or a tool error is
recorded as an outcome and the gate reports exit 2 (cannot check); nothing crashes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from . import AS_OF, RELAY, gate_policy
from .gates import decide
from .sarif import load_sarif

COMMANDS = {
    "semgrep": ["semgrep", "scan", "--config", str(RELAY / "security" / "semgrep.yml"), "--metrics=off",
                "--sarif", "--output", "{out}", str(RELAY)],
    "gitleaks": ["gitleaks", "dir", str(RELAY), "--config", str(RELAY / "security" / "gitleaks.toml"),
                 "--report-format", "sarif", "--report-path", "{out}", "--exit-code", "0"],
    "trivy": ["trivy", "fs", "--offline-scan", "--scanners", "vuln,misconfig", "--format", "sarif",
              "--output", "{out}", str(RELAY)],
}


def main() -> int:
    if os.environ.get("SECLOOP_LIVE") != "1":
        sys.stderr.write("live mode is off; set SECLOOP_LIVE=1 to run the installed scanners\n")
        return 2
    present, findings, outcomes = set(), [], {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, cmd in COMMANDS.items():
            out = Path(tmp) / f"{name}.sarif"
            if shutil.which(cmd[0]) is None:
                outcomes[name] = "not installed"
                continue
            try:
                proc = subprocess.run([c.replace("{out}", str(out)) for c in cmd], capture_output=True, text=True,
                                      timeout=600)
                outcomes[name] = f"exit {proc.returncode}"
                if out.exists():
                    for f in load_sarif(out):
                        findings.append(f.__class__(name, f.rule, f.severity, "live", f.path, f.line,
                                                    f.fingerprint, f.message))
                    present.add(name)
            except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, KeyError) as exc:
                outcomes[name] = f"error: {type(exc).__name__}"
    result = decide(findings, gate_policy(), [], date.fromisoformat(AS_OF), "ci", present)
    sys.stdout.write(json.dumps({"tools": outcomes, "gate_exit": result.status, "missing": result.missing,
                                 "blocking": len(result.blocking), "warnings": len(result.warnings)},
                                indent=2) + "\n")
    return result.status


if __name__ == "__main__":
    raise SystemExit(main())
