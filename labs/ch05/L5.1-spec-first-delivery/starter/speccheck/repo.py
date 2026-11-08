"""Find the tests in a repository and the IDs their names carry.

A test for acceptance criterion ESC-AC08 is named `test_ESC_AC08` or
`test_ESC_AC08_<anything>`; a policy test for security constraint SEC-03 is
named `test_SEC03...`. Tests are found by reading the source with `ast`, so
nothing is imported or run.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CRITERION_TEST = re.compile(r"^test_([A-Z]+)_AC(\d+)(?:_|$)")
CONSTRAINT_TEST = re.compile(r"^test_SEC(\d+)(?:_|$)")


def find_tests(tests_dir: Path) -> tuple[str, ...]:
    """Names of every test function under `tests_dir`, sorted."""
    names = set()
    for path in sorted(Path(tests_dir).rglob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                names.add(node.name)
    return tuple(sorted(names))


def criterion_of(test_name: str) -> str | None:
    """'test_ESC_AC08_first_step' -> 'ESC-AC08'; None if the name carries no criterion ID."""
    m = CRITERION_TEST.match(test_name)
    return f"{m.group(1)}-AC{m.group(2)}" if m else None


def constraint_of(test_name: str) -> str | None:
    """'test_SEC03_evaluator_never_reads_suggestions' -> 'SEC-03'."""
    m = CONSTRAINT_TEST.match(test_name)
    return f"SEC-{m.group(1)}" if m else None
