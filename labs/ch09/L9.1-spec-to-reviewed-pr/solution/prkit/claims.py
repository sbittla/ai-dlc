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
    create = re.compile(rf"CREATE TABLE (?:IF NOT EXISTS )?{re.escape(table)} \((.*?)\n\);", re.S)
    for path in _py(repo, "src"):
        text = path.read_text(encoding="utf-8")
        m = create.search(text)
        if not m:
            continue
        line = text[: m.start()].count("\n") + 1
        check = re.search(rf"{re.escape(column)}\b[^,\n]*CHECK \({re.escape(column)} IN \(([^)]*)\)\)", m.group(1))
        where = f"{_rel(repo, path)}:{line}"
        if not check:
            return None, where
        return [v.strip().strip("'") for v in check.group(1).split(",")], where
    raise LookupError(f"no CREATE TABLE {table} in src/")


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
    kind, cid = claim["kind"], claim["id"]
    if kind == "table_users":
        ev = table_users(repo, claim["table"])
        return Verdict(cid, files_of(ev) == set(claim["expect"]), tuple(ev[:5]))
    if kind == "callers":
        ev = callers(repo, claim["function"], claim["scope"])
        return Verdict(cid, files_of(ev) == set(claim["expect"]), tuple(ev[:5]))
    if kind == "tests_matching":
        ev = tests_matching(repo, claim["pattern"])
        return Verdict(cid, len(ev) == claim["expect"], (f"{len(ev)} matching line(s)",) + tuple(ev[:4]))
    if kind == "check_constraint":
        values, where = check_values(repo, claim["table"], claim["column"])
        accepts = values is None or claim["value"] in values
        shown = "no CHECK" if values is None else "CHECK IN (" + ", ".join(values) + ")"
        return Verdict(cid, accepts == claim["expect"], (where, shown))
    if kind == "imports":
        ev = imports_module(repo, claim["package"], claim["module"])
        return Verdict(cid, bool(ev) == claim["expect"], tuple(ev[:5]) or (f"no import of {claim['module']}",))
    if kind == "openapi_operations":
        n = openapi_operations(repo)
        return Verdict(cid, n == claim["expect"], (f"{n} operation(s)",))
    if kind == "matrix_row":
        ev = matrix_rows(repo, claim["method"], claim["status"])
        return Verdict(cid, bool(ev) == claim["expect"], tuple(ev[:5]) or ("no such row",))
    raise ValueError(f"{cid}: unknown claim kind {kind!r}")


def verify_all(repo: Path, claims_file: Path) -> list[tuple[dict, Verdict]]:
    claims = json.loads(claims_file.read_text(encoding="utf-8"))["claims"]
    return [(c, verify_claim(repo, c)) for c in claims]
