"""Build the canonical Relay 4.19.0 from the two Batch 2 branches.

Chapter 5 (Relay 4.18.0) added `relay/escalation/`, its tests and `specs/`.
Chapter 6 (its own 4.19.0) added `relay/service/`, `relay/worker/`, ADRs and
architecture tests. Both started from 4.17.2 and touched disjoint packages.
This script combines them deterministically:

    python labs/relay-baselines/merge_4_19_0.py

Output: labs/relay-baselines/4.19.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import shutil
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
CH5 = LABS / "ch05/L5.1-spec-first-delivery/solution/relay-repo"
CH6 = LABS / "ch06/L6.1-architecture-options-adr/relay-repo"
OUT = LABS / "relay-baselines/4.19.0/relay-repo"
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*")

ESCALATION_MODULES = ["relay.escalation", "relay.escalation.model", "relay.escalation.rules",
                      "relay.escalation.evaluate", "relay.escalation.contract"]


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def write(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def insert_after(text: str, anchor: str, addition: str) -> str:
    if text.count(anchor) != 1:
        raise SystemExit(f"anchor not found exactly once: {anchor!r}")
    return text.replace(anchor, anchor + addition)


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH6, OUT, ignore=IGNORE)
    shutil.copytree(CH5 / "src/relay/escalation", OUT / "src/relay/escalation", ignore=IGNORE)
    shutil.copytree(CH5 / "tests/escalation", OUT / "tests/escalation", ignore=IGNORE)
    shutil.copytree(CH5 / "specs", OUT / "specs", ignore=IGNORE)

    agents, nl = read(OUT / "AGENTS.md")
    agents = insert_after(
        agents,
        "- Decisions: `docs/adr/`. `tests/test_architecture.py` enforces ADR-007's module boundaries.\n",
        "- `src/relay/escalation/`: escalation rule validation and evaluation, built from `specs/001-escalation-rules/`.\n"
        "- `specs/`: approved specifications. Change a spec in its own pull request before the code that follows it.\n",
    )
    agents = insert_after(
        agents,
        "- Write the failing test first, in `tests/`, named after the ticket (for example `test_due_dates_rly412.py`).\n",
        "- Name a test for an acceptance criterion after the criterion: `test_ESC_AC08_...` checks ESC-AC08.\n",
    )
    write(OUT / "AGENTS.md", agents, nl)

    owners, nl = read(OUT / ".github/CODEOWNERS")
    ch5_lines = [line for line in read(CH5 / ".github/CODEOWNERS")[0].splitlines()
                 if line.startswith(("/specs/", "/src/relay/escalation/", "/tests/escalation/"))]
    owners = owners.rstrip("\n") + "\n" + "\n".join(ch5_lines) + "\n"
    write(OUT / ".github/CODEOWNERS", owners, nl)

    arch, nl = read(OUT / "tests/test_architecture.py")
    old = 'DOMAIN = {"relay", "relay.api", "relay.duedates", "relay.models", "relay.roles", "relay.store", "relay.timezones"}'
    new = (old[:-1] + ",\n          " + ", ".join(f'"{m}"' for m in ESCALATION_MODULES[:3]) + ",\n          "
           + ", ".join(f'"{m}"' for m in ESCALATION_MODULES[3:]) + "}")
    if arch.count(old) != 1:
        raise SystemExit("DOMAIN line not found")
    write(OUT / "tests/test_architecture.py", arch.replace(old, new), nl)

    print(f"wrote canonical Relay 4.19.0 to {OUT}")


if __name__ == "__main__":
    main()
