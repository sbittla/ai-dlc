"""secloop: Lab 13.1's security gates for an agent's coding loop.

Gates over scanner reports (gates), a dependency gate (deps), re-verification of fixes (fixes), catch
rates with intervals (catch) and a release-evidence check (release). The scanner reports are simulated
SARIF in data/scans/; live.py can produce real ones when the tools are installed (optional, gated).
"""

import json
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
RELAY = LAB_ROOT / "relay-repo"
AS_OF = "2027-01-28"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def gate_policy() -> dict:
    return load_json(RELAY / "security" / "gates.json")


def mirror_policy() -> dict:
    return load_json(RELAY / "supply-chain" / "mirror.json")
