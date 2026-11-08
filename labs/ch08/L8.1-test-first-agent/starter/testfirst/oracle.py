"""The oracle-independence check: does a test's expected value come from the code it tests?

A test oracle decides whether an output is right. If the expected value is
computed by calling the code under test, the test compares the code with
itself: it passes whatever the code does, and it would have passed with the
bug. This check reads test files with `ast` and reports three patterns.

    OI01  An assertion compares two values that both come from the code under test
          (a call into it, or a value derived from one).                     blocking
    OI02  A test function with no assert statement and no pytest.raises.       blocking
    OI03  An assertion checks only that a result from the code under test is
          truthy, not None, or non-empty: it cannot say whether it is right.  warning

OI01 over-approximates on purpose. Comparing the code with itself on
*different* inputs is a metamorphic oracle, not a self-confirming one: two
delays that add up, or a refusal that leaves a rule unchanged. `check_files`
therefore exempts, and reports as exempt, OI01 and OI03 findings in two places:

- tests decorated with `@for_all` (properties, whose oracle is the stated law);
- assertions whose line carries a reviewed marker, `# oracle: <kind> - <why>`.

An exemption is a claim a reviewer reads, like an equivalent mutant.

It is a static check, so it is easy to evade. It follows names assigned in a
test and helper functions defined in the same test file. It does not follow
pytest fixtures (a value arriving as a parameter), helpers imported from other
files such as escalation_fixtures.py, or a module imported under an alias
(`import relay.escalation.delivery as d`). OI03 also flags any bare
`assert f(...)`, including legitimate boolean predicates. The human review of
each test against its criterion remains the main control.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

BLOCKING = {"OI01", "OI02"}
TITLES = {
    "OI01": "expected value computed by the code under test",
    "OI02": "test asserts nothing",
    "OI03": "assertion checks only that a result is truthy, present or non-empty",
}


@dataclass(frozen=True)
class Finding:
    code: str
    test: str
    line: int
    detail: str
    exempt: str | None = None  # why a reviewer accepted it: "property" or the marker's text

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING and self.exempt is None

    def row(self) -> str:
        note = f" (exempt: {self.exempt})" if self.exempt else ""
        return f"| {self.code} | `{self.test}` | {self.line} | {TITLES[self.code]}: {self.detail}{note} |"


def imported_names(tree: ast.Module, modules: tuple[str, ...]) -> set[str]:
    """Names a test module imports from the modules under test, e.g. {'add_business_minutes', 'run_pass'}."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if any(node.module == m or node.module.startswith(m + ".") for m in modules):
                names |= {a.asname or a.name for a in node.names}
    return names


def calls_into(node: ast.AST, under_test: set[str]) -> bool:
    """True if `node` contains, anywhere, a direct call to a name under test."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in under_test:
                return True
    return False


def carries(node: ast.AST, under_test: set[str], tainted: set[str]) -> bool:
    """True if the value of `node` comes from the code under test.

    A call to a name under test, or a method called on such a value, carries
    the taint; so do names assigned from such values, and anything built from
    them (attributes, items, arithmetic, f-strings, tuples). A call to any other
    function, such as hmac.new or json.dumps, starts a new value: recomputing an
    expected value independently from an output is a legitimate oracle.
    """
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in under_test
        if isinstance(func, ast.Attribute):
            return func.attr in under_test or carries(func.value, under_test, tainted)
        return False
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        return carries(node.value, under_test, tainted)
    if isinstance(node, ast.Constant):
        return False
    return any(carries(child, under_test, tainted) for child in ast.iter_child_nodes(node)
               if isinstance(child, ast.expr) or isinstance(child, ast.comprehension))


def depends(node: ast.AST, under_test: set[str], tainted: set[str]) -> bool:
    """A side of an assertion depends on the code under test if it carries its value or calls it directly."""
    return carries(node, under_test, tainted) or calls_into(node, under_test)


def tainted_names(func: ast.FunctionDef, under_test: set[str], helpers: set[str] = frozenset()) -> set[str]:
    """Local names whose value comes, directly or through other names, from the code under test.

    `helpers` are module-level functions of the test file that themselves call
    the code under test; calling one taints its result too. Assignments are
    walked in source order until nothing new is tainted.
    """
    raise NotImplementedError("TODO (Lab 8.1, step 4: follow values from the code under test)")


def _helpers(tree: ast.Module, under_test: set[str]) -> set[str]:
    """Module-level functions (not tests) whose bodies call the code under test, directly or via each other."""
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("test")}
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, node in funcs.items():
            if name not in found and calls_into(node, under_test | found):
                found.add(name)
                changed = True
    return found


def _is_existence_check(test: ast.expr) -> ast.expr | None:
    """The operand of `assert x`, `assert x is not None`, `assert len(x)`, or None for anything else."""
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.IsNot) \
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None:
        return test.left
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id in ("len", "bool"):
        return test.args[0] if test.args else None
    if isinstance(test, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
        return test
    return None


def check_oracles(source: str, filename: str, modules: tuple[str, ...]) -> list[Finding]:
    """OI01, OI02 and OI03 for every test function in one test file's `source`."""
    raise NotImplementedError("TODO (Lab 8.1, step 4: OI01, OI02 and OI03)")


def exemptions(source: str) -> tuple[set[str], dict[int, str]]:
    """(tests decorated with @for_all, {line: marker text}) for one test file."""
    tree = ast.parse(source)
    props = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                func = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(func, ast.Name) and func.id == "for_all":
                    props.add(node.name)
    markers = {n: line.split("# oracle:", 1)[1].strip()
               for n, line in enumerate(source.splitlines(), 1) if "# oracle:" in line}
    return props, markers


def check_files(paths: list[Path], modules: tuple[str, ...]) -> list[Finding]:
    """check_oracles for each file, with property tests and reviewed markers marked exempt."""
    out = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        props, markers = exemptions(source)
        for f in check_oracles(source, str(path), modules):
            if f.code in ("OI01", "OI03") and f.test in props:
                f = Finding(f.code, f.test, f.line, f.detail, "property")
            elif f.code in ("OI01", "OI03") and f.line in markers:
                f = Finding(f.code, f.test, f.line, f.detail, markers[f.line])
            out.append(f)
    return out
