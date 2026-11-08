"""Copy Relay 4.20.0's source, escalation tests and spec package into data/relay-repo (deterministic).

    python scripts/generate_data.py

The copy comes from Lab 8.1's reference solution in the same chapter, so that
this lab mutates exactly the code Chapter 8 ships. Line endings are written as
LF on every platform. Not generated (lab input): data/weak-suite/,
data/mutation-policy.json and data/equivalent-mutants.json.
"""

from __future__ import annotations

import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
SOURCE = LAB.parent / "L8.1-test-first-agent" / "solution" / "relay-repo"
TARGET = LAB / "data" / "relay-repo"
COPY = ("src/relay", "tests/escalation", "specs/001-escalation-rules")


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    count = 0
    for rel in COPY:
        for path in sorted((SOURCE / rel).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix not in (".py", ".md", ".json"):
                continue
            out = TARGET / path.relative_to(SOURCE)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            count += 1
    print(f"copied {count} files from Relay 4.20.0 into {TARGET.relative_to(LAB).as_posix()}")


if __name__ == "__main__":
    main()
