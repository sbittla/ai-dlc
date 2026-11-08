"""Regenerate tests/golden/ from the reference solution (instructors only; takes a few minutes).

    cd solution
    python ../scripts/update_golden.py
"""

import os
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
os.environ["LAB_TARGET"] = "solution"   # tests/conftest.py puts solution/ on the path
sys.path.insert(0, str(LAB / "tests"))

from test_golden import outputs  # noqa: E402


def main() -> None:
    out = LAB / "tests" / "golden"
    out.mkdir(exist_ok=True)
    for name, fn in outputs().items():
        (out / f"{name}.md").write_text(fn() + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(outputs())} golden files to {out}")


if __name__ == "__main__":
    main()
