"""Mutation operators: small, deliberate faults put into a copy of the code (standard library only).

Each mutant changes one node of a module's syntax tree. The operators are the
classic ones that find weak assertions:

    ROR  relational operator replacement   <  <=  >  >=  ==  !=  in  not in  is  is not
    AOR  arithmetic operator replacement   +  -
    CRP  constant replacement              an integer n becomes n + 1 and n - 1; True and False swap
    LCR  logical connector replacement     and  or
    NEG  negation removal                  `not x` becomes `x`
    RSD  raise statement deletion          `raise ...` becomes `pass`

Docstrings, annotations, `from __future__` lines and the arguments of raise
statements are not mutated: a fault there changes no behaviour a test should see.
What tools such as mutmut, Cosmic Ray or PIT add: many more operators, parallel
runs, caching between runs, incremental runs on changed lines only, and HTML reports.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

ROR = {ast.Lt: [ast.LtE], ast.LtE: [ast.Lt], ast.Gt: [ast.GtE], ast.GtE: [ast.Gt], ast.Eq: [ast.NotEq],
       ast.NotEq: [ast.Eq], ast.In: [ast.NotIn], ast.NotIn: [ast.In], ast.Is: [ast.IsNot], ast.IsNot: [ast.Is]}
AOR = {ast.Add: ast.Sub, ast.Sub: ast.Add}
SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in",
          ast.NotIn: "not in", ast.Is: "is", ast.IsNot: "is not", ast.Add: "+", ast.Sub: "-", ast.And: "and",
          ast.Or: "or"}


@dataclass(frozen=True)
class Mutant:
    id: str  # "<file>:<line>:<col>:<operator>:<change>", stable across runs
    file: str
    line: int
    operator: str
    change: str
    source: str  # the whole mutated module


def _skipped_nodes(tree: ast.AST) -> set[int]:
    """ids of nodes that are never mutated: docstrings, annotations, __future__ imports, raise arguments."""
    skip: set[int] = set()

    def mark(node):
        for sub in ast.walk(node):
            skip.add(id(sub))

    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            mark(body[0])
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                if arg.annotation is not None:
                    mark(arg.annotation)
            if node.returns is not None:
                mark(node.returns)
        if isinstance(node, ast.AnnAssign):
            mark(node.annotation)
        if isinstance(node, ast.ImportFrom):
            mark(node)
        if isinstance(node, ast.Raise) and node.exc is not None:
            mark(node.exc)
    return skip


def candidates(tree: ast.AST) -> list[tuple[int, str, str, object]]:
    """(node index in ast.walk order, operator, change, replacement) for every mutation of `tree`."""
    skip = _skipped_nodes(tree)
    out = []
    for index, node in enumerate(ast.walk(tree)):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                for new in ROR.get(type(op), []):
                    out.append((index, "ROR", f"{SYMBOL[type(op)]} -> {SYMBOL[new]}", ("cmp", k, new)))
        elif isinstance(node, ast.BinOp) and type(node.op) in AOR:
            new = AOR[type(node.op)]
            out.append((index, "AOR", f"{SYMBOL[type(node.op)]} -> {SYMBOL[new]}", ("binop", new)))
        elif isinstance(node, ast.BoolOp):
            new = ast.Or if isinstance(node.op, ast.And) else ast.And
            out.append((index, "LCR", f"{SYMBOL[type(node.op)]} -> {SYMBOL[new]}", ("boolop", new)))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            out.append((index, "NEG", "not x -> x", ("unnot",)))
        elif isinstance(node, ast.Raise):
            out.append((index, "RSD", "raise -> pass", ("raise",)))
        elif isinstance(node, ast.Constant) and type(node.value) is bool:
            out.append((index, "CRP", f"{node.value} -> {not node.value}", ("const", not node.value)))
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            for delta in (1, -1):
                out.append((index, "CRP", f"{node.value} -> {node.value + delta}", ("const", node.value + delta)))
    return out


def _apply(tree: ast.AST, index: int, replacement) -> ast.AST:
    tree = copy.deepcopy(tree)
    nodes = list(ast.walk(tree))
    target = nodes[index]
    kind = replacement[0]
    if kind == "cmp":
        target.ops[replacement[1]] = replacement[2]()
    elif kind == "binop":
        target.op = replacement[1]()
    elif kind == "boolop":
        target.op = replacement[1]()
    elif kind == "const":
        target.value = replacement[1]
    elif kind in ("unnot", "raise"):
        new = target.operand if kind == "unnot" else ast.Pass()
        for parent in nodes:
            for name, value in ast.iter_fields(parent):
                if value is target:
                    setattr(parent, name, new)
                elif isinstance(value, list) and any(v is target for v in value):
                    setattr(parent, name, [new if v is target else v for v in value])
    return ast.fix_missing_locations(tree)


def mutants(source: str, file: str) -> list[Mutant]:
    """Every mutant of one module, in a stable order (by line, column, then operator and change)."""
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    found = []
    for index, operator, change, replacement in candidates(tree):
        node = nodes[index]
        line, col = getattr(node, "lineno", 0), getattr(node, "col_offset", 0)
        mutated = ast.unparse(_apply(tree, index, replacement))
        found.append(Mutant(f"{file}:{line}:{col}:{operator}:{change}", file, line, operator, change, mutated))
    return sorted(found, key=lambda m: (m.line, int(m.id.split(":")[2]), m.operator, m.change))
