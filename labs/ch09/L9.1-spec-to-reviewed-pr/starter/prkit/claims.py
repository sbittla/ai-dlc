"""Check an agent's claims about a repository against its source and tests (Lab 9.1, Section 9.1).

An agent's account of the code is a set of claims, and each claim is either
checkable or not. This module checks seven kinds, by reading the files with
`ast` and regular expressions; it never imports or runs the code. A verdict
is True when the claim matches the source, False when it does not, and the
evidence names the files and lines that decided it.

| Kind | The claim says | Checked by |
| --- | --- | --- |
| table_users | only these files mention a table in their SQL | every string in src/ that names the table |
| callers | only these files call a function | every call by name or attribute in the scope |
| tests_matching | this many test lines match a pattern | a regular expression over tests/ |
| check_constraint | a column accepts a value | the CHECK (column IN (...)) in the table's CREATE TABLE |
| imports | a package imports a module | every import statement in the package |
| openapi_operations | the OpenAPI description has this many operations | the JSON file |
| matrix_row | the refusal matrix has a row for this method and status | tests/service_helpers.py |
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

HTTP_METHODS = {"get", "put", "post", "delete", "patch"}


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    holds: bool
    evidence: tuple[str, ...]  # "path:line" or a short fact, at most five


def _py(repo: Path, scope: str) -> list[Path]:
    return sorted(p for p in (repo / scope).rglob("*.py") if "__pycache__" not in p.parts)


def _rel(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


def table_users(repo: Path, table: str) -> list[str]:
    """'path:line' for every string literal in src/ that names `table` as a whole word."""
    word = re.compile(rf"\b{re.escape(table)}\b")
    found = []
    for path in _py(repo, "src"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and word.search(node.value):
                found.append(f"{_rel(repo, path)}:{node.lineno}")
    return sorted(set(found), key=lambda s: (s.split(":")[0], int(s.split(":")[1])))


def callers(repo: Path, function: str, scope: str) -> list[str]:
    """'path:line' for every call of `function`, as a name or an attribute, under `scope`."""
    found = []
    for path in _py(repo, scope):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if name == function:
                    found.append(f"{_rel(repo, path)}:{node.lineno}")
    return found


def files_of(evidence: list[str]) -> set[str]:
    return {e.split(":")[0] for e in evidence}


def tests_matching(repo: Path, pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [f"{_rel(repo, p)}:{n}" for p in _py(repo, "tests")
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if rx.search(line)]


def check_values(repo: Path, table: str, column: str) -> tuple[list[str] | None, str]:
    """The values `column` is constrained to in `table`'s CREATE TABLE, or None if unconstrained; and where."""
    # TODO (README step 2: find the CHECK (column IN (...)) clause)
    raise NotImplementedError("TODO: check_values (README step 2: find the CHECK (column IN (...)) clause)")


def imports_module(repo: Path, package: str, module: str) -> list[str]:
    """'path:line' for every import of `module` (or a submodule) in the package, relative imports resolved."""
    found = []
    for path in _py(repo, package):
        parts = list(path.relative_to(repo / "src").with_suffix("").parts)  # e.g. relay, worker, runner
        if parts[-1] == "__init__":
            parts.pop()
        pkg = parts if path.name == "__init__.py" else parts[:-1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = pkg[: len(pkg) - node.level + 1] if node.level else []
                names = [".".join(base + ([node.module] if node.module else []))]
            if any(n == module or n.startswith(module + ".") for n in names):
                found.append(f"{_rel(repo, path)}:{node.lineno}")
    return found


def openapi_operations(repo: Path) -> int:
    [path] = sorted((repo / "specs").rglob("*.openapi.json"))
    api = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for ops in api["paths"].values() for m in ops if m in HTTP_METHODS)


def matrix_rows(repo: Path, method: str, status: int) -> list[str]:
    path = repo / "tests" / "service_helpers.py"
    rx = re.compile(rf"""["']{method}["'].*?,\s*{status},""")
    return [f"tests/service_helpers.py:{n}" for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if rx.search(line)]


def verify_claim(repo: Path, claim: dict) -> Verdict:
    """Check one claim (a dict from data/agent-claims.json) against the repository at `repo`."""
    # TODO (README step 2: dispatch on claim['kind'] to the helpers)
    raise NotImplementedError("TODO: verify_claim (README step 2: dispatch on claim['kind'] to the helpers)")


def verify_all(repo: Path, claims_file: Path) -> list[tuple[dict, Verdict]]:
    claims = json.loads(claims_file.read_text(encoding="utf-8"))["claims"]
    return [(c, verify_claim(repo, c)) for c in claims]
