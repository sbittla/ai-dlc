"""Point the tests at starter/ (default) or solution/.

    python -m pytest                      # grade your work in starter/
    LAB_TARGET=solution python -m pytest  # check the reference solution (bash)
    $env:LAB_TARGET="solution"; python -m pytest   # same, PowerShell
"""

import json
import os
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
TARGET = os.environ.get("LAB_TARGET", "starter")
if TARGET not in {"starter", "solution"}:
    raise SystemExit(f"LAB_TARGET must be 'starter' or 'solution', got {TARGET!r}")

sys.path.insert(0, str(LAB_ROOT / TARGET))
DATA_DIR = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
POLICY = json.loads((DATA_DIR / "policy.json").read_text(encoding="utf-8"))
PRICES = json.loads((DATA_DIR / "prices" / "aws-us-east-1-2026-11.json").read_text(encoding="utf-8"))


def rc(type_, name, after, unknown=None, config=None, actions=("create",), index=None, before=None):
    """One resource change, written by hand. `config` is the configuration's expressions."""
    entry = {"address": f"{type_}.{name}" + (f"[{index}]" if index is not None else ""), "mode": "managed",
             "type": type_, "name": name, "provider_name": "registry.opentofu.org/hashicorp/aws",
             "change": {"actions": list(actions), "before": before, "after": after,
                        "after_unknown": unknown or {}}}
    if index is not None:
        entry["index"] = index
    return entry, {"address": f"{type_}.{name}", "type": type_, "name": name, "expressions": config or {}}


def mkplan(*entries, variables=None, region="us-east-1"):
    """A minimal plan in the `tofu show -json` shape, from rc() entries."""
    return {"format_version": "1.2", "variables": {k: {"value": v} for k, v in (variables or {}).items()},
            "planned_values": {"root_module": {"resources": []}},
            "resource_changes": [e for e, _ in entries],
            "configuration": {"provider_config": {"aws": {"expressions": {"region": {"constant_value": region}}}},
                              "root_module": {"resources": [c for _, c in entries]}}}


def ref(address):
    return {"references": [f"{address}.id", address]}


def pytest_report_header(config):
    return f"Lab 11.1 tests running against: {TARGET}/"
