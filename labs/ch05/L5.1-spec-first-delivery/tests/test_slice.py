"""The escalation slice in <target>/relay-repo: its own suite, lint, the contract, and what changed.

Until you implement validate_rule and evaluate (README step 5) and complete the
spec's data rules (step 3), these tests stop with NotImplementedError.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from conftest import DATA_DIR, RELAY_REPO, SPEC_DIR_NAME

ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
UTC = timezone.utc

# Relay 4.18.0 may change only these 4.17.2 files (version string, instruction file, code owners)...
MODIFIED = {"src/relay/__init__.py", "pyproject.toml", "AGENTS.md", ".github/CODEOWNERS"}
# ...and may add files only under these paths.
ADDED_UNDER = ("src/relay/escalation/", "tests/escalation/", f"specs/{SPEC_DIR_NAME}/")
IGNORED = ("__pycache__", ".pytest_cache")


def run_suite():
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=RELAY_REPO, env=ENV,
                          capture_output=True, text=True, timeout=180)
    lines = proc.stdout.strip().splitlines()
    return proc.returncode, proc.stdout, lines[-1] if lines else proc.stderr


def test_relay_suite_passes():
    code, out, last = run_suite()
    if code != 0 and "NotImplementedError" in out:
        raise NotImplementedError("relay-repo's escalation tests stop with NotImplementedError: "
                                  "implement validate_rule and evaluate, and complete the spec (README steps 3 and 5)")
    assert code == 0, last


def test_relay_lint_passes():
    lint = subprocess.run([sys.executable, "tools/lint.py"], cwd=RELAY_REPO, env=ENV, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout


def test_evaluation_document_conforms_to_the_contract():
    from relay.escalation import EscalationState, Rule, Step, evaluate, to_document, validate
    from relay.models import Task
    schema = json.loads((RELAY_REPO / "specs" / SPEC_DIR_NAME / "contracts" / "escalation-rules.schema.json")
                        .read_text(encoding="utf-8"))
    t0 = datetime(2026, 11, 24, 2, 30, tzinfo=UTC)
    rule = Rule("R1", 10, "P1", (Step(1, 10, (5,)), Step(2, 20, (2,))))
    state = EscalationState(task_id=7, priority="P1", priority_set_at=t0)
    result = evaluate(rule, Task(7, 10, "Customer 4471 card data exposed"), state, t0 + timedelta(minutes=25))
    document = to_document(result)
    assert validate(document, {"$ref": "#/$defs/Evaluation"}, schema) == []
    assert document["fire"] == [{"step": 1, "targets": [5], "due_at": "2026-11-24T02:40:00Z"},
                                {"step": 2, "targets": [2], "due_at": "2026-11-24T02:50:00Z"}]
    assert (document["status"], document["next_due_at"]) == ("complete", None)


def test_version_is_4_18_0():
    import relay
    from relay import escalation
    assert relay.__version__ == "4.18.0" and escalation.SPEC_VERSION == "1.0.0"


def _digest(path):
    # Line endings are normalised so that a Windows checkout with autocrlf hashes the same.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_changes_to_relay_stay_inside_the_escalation_slice():
    baseline = json.loads((DATA_DIR / "relay-4.17.2-manifest.json").read_text(encoding="utf-8"))["sha256"]
    files = {p.relative_to(RELAY_REPO).as_posix(): p for p in RELAY_REPO.rglob("*")
             if p.is_file() and not any(part in IGNORED for part in p.parts)}
    assert set(baseline) <= set(files), sorted(set(baseline) - set(files))
    changed = {name for name, digest in baseline.items() if _digest(files[name]) != digest}
    assert changed <= MODIFIED, sorted(changed - MODIFIED)
    added = sorted(set(files) - set(baseline))
    assert all(name.startswith(ADDED_UNDER) for name in added), [n for n in added if not n.startswith(ADDED_UNDER)]
