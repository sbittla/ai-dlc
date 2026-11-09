"""Write Lab 9.1's GENERATED data (deterministic; byte-identical on every platform).

    python scripts/generate_data.py

- data/relay-4.21.0/: the parts of canonical Relay 4.21.0 a review reads (src, tests, specs, docs,
  AGENTS.md, .github/CODEOWNERS, pyproject.toml), copied byte for byte from labs/relay-baselines/4.21.0/.
  It is the base the pull requests are measured from, and the code the agent's claims are checked against.
- data/prd-v1.1.md: PRD v1.1, copied from Lab 8.1, which spec 1.2.0 is derived from.

The other files in data/ are inputs, written by hand: pr-plan.json, incident-pr.json, agent-claims.json.
"""

from __future__ import annotations

import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
LABS = LAB.parent.parent
BASE = LABS / "relay-baselines" / "4.21.0" / "relay-repo"
PRD = LABS / "ch08" / "L8.1-test-first-agent" / "data" / "prd-v1.1.md"
OUT = LAB / "data" / "relay-4.21.0"
TREES = ("src", "tests", "specs", "docs")
FILES = ("AGENTS.md", ".github/CODEOWNERS", "pyproject.toml")


def copy_bytes(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def main() -> None:
    if not BASE.is_dir():
        raise SystemExit(f"canonical Relay 4.21.0 not found at {BASE}")
    if OUT.exists():
        shutil.rmtree(OUT)
    count = 0
    for top in TREES:
        for p in sorted((BASE / top).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                copy_bytes(p, OUT / p.relative_to(BASE))
                count += 1
    for name in FILES:
        copy_bytes(BASE / name, OUT / name)
        count += 1
    copy_bytes(PRD, LAB / "data" / "prd-v1.1.md")
    print(f"wrote {count} files to {OUT.relative_to(LAB)} and data/prd-v1.1.md")


if __name__ == "__main__":
    main()
