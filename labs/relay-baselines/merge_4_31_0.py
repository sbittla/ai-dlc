"""Build the canonical Relay 4.31.0 from the Batch 8 branches.

Chapter 19 (Relay 4.31.0) added the maintenance bot: `relay/maintenance/`,
`maintenance/` policy, its workflow and registry entry, guard paths, and
ADR-053 to ADR-056. Chapter 20 made no Relay changes. So canonical 4.31.0 is
Chapter 19's tree, copied deterministically:

    python labs/relay-baselines/merge_4_31_0.py

Output: labs/relay-baselines/4.31.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import shutil
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
CH19 = LABS / "ch19/L19.1-maintenance-bot/relay-repo"
CH20 = LABS / "ch20/L20.1-maturity-operating-model-roi/relay-repo"
OUT = LABS / "relay-baselines/4.31.0/relay-repo"
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*", "*.egg-info", "evidence",
                                ".venv", "venv")


def main() -> None:
    if not CH19.is_dir():
        raise SystemExit(f"missing tree: {CH19}")
    if CH20.exists():
        raise SystemExit("Chapter 20 now ships a Relay branch; merge it by hand")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH19, OUT, ignore=IGNORE)
    print(f"wrote canonical Relay 4.31.0 to {OUT}")


if __name__ == "__main__":
    main()
