"""Write Lab 10.2's generated data (deterministic; run from anywhere).

    python scripts/generate_data.py

Copies Relay 4.24.0's `relay.agents` and `relay.audit` packages (and `relay/__init__.py`) from Lab 10.1's
reference solution into data/relay-4.24.0/src/relay/, so this lab runs the same runtime code. Nothing else
is generated; data/faults.json is written by hand.
"""

from __future__ import annotations

import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
SOURCE = LAB.parent / "L10.1-workflow-agent-multiagent" / "solution" / "relay-repo" / "src" / "relay"
TARGET = LAB / "data" / "relay-4.24.0" / "src" / "relay"


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    init = (SOURCE / "__init__.py").read_text(encoding="utf-8")
    (TARGET / "__init__.py").write_text(init, encoding="utf-8", newline="\n")
    for package in ("agents", "audit"):
        (TARGET / package).mkdir()
        for path in sorted((SOURCE / package).glob("*.py")):
            text = path.read_text(encoding="utf-8")
            (TARGET / package / path.name).write_text(text, encoding="utf-8", newline="\n")
    print(f"copied relay.agents and relay.audit to {TARGET}")


if __name__ == "__main__":
    main()
