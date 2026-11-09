"""A small standard-library linter for Relay's snapshot.

    python tools/lint.py

Checks every .py file under src/ and tests/: it compiles, has no tabs, no
line over 120 characters, no stray breakpoint() and no print() in src/.
Exit status 1 if anything is found.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def lint(root: Path = ROOT) -> list[str]:
    problems = []
    for folder in ("src", "tests"):
        for path in sorted((root / folder).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            try:
                compile(text, rel, "exec")
            except SyntaxError as exc:
                problems.append(f"{rel}:{exc.lineno}: syntax error")
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if "\t" in line:
                    problems.append(f"{rel}:{n}: tab character")
                if len(line) > 120:
                    problems.append(f"{rel}:{n}: line longer than 120 characters")
                if "breakpoint()" in line:
                    problems.append(f"{rel}:{n}: breakpoint() left in")
                if folder == "src" and line.lstrip().startswith("print("):
                    problems.append(f"{rel}:{n}: print() in library code")
    return problems


def main() -> None:
    problems = lint()
    for p in problems:
        print(p)
    print(f"lint: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
