"""Load a repository (with an optional overlay) and build its import graph.

TODO 1 (imports_of) is yours in starter/. Everything else is provided.

The tool reads source text with `ast`; it never imports or runs the code it
checks. That makes it safe to run on untrusted pull requests, and blind to
anything decided at run time (Chapter 6, Section 6.5).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Import:
    line: int
    target: str      # absolute dotted module name, e.g. "relay.worker.queue" or "urllib.request"


def load_tree(repo: str | Path, overlay: str | Path | None = None) -> dict[str, str]:
    """{posix relative path: text} for every file under repo, with overlay files replacing or adding."""
    files = {}
    for base in [Path(repo)] + ([Path(overlay)] if overlay else []):
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files[p.relative_to(base).as_posix()] = p.read_text(encoding="utf-8")
    return files


def module_name(path: str, src: str = "src") -> str | None:
    """'src/relay/worker/queue.py' -> 'relay.worker.queue'; '…/__init__.py' -> the package. None if not code."""
    if not path.startswith(src + "/") or not path.endswith(".py"):
        return None
    parts = path[len(src) + 1:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports_of(source: str, module: str, is_package: bool) -> list[Import]:
    """TODO 1. Every static import in `source`, as absolute module names, in line order.

    `module` is the dotted name of the file being read; `is_package` is True for an
    __init__.py. Walk the whole tree (imports inside functions and `if` blocks count).
    - `import a.b, c` gives "a.b" and "c" (one Import each).
    - `from a.b import x` gives "a.b" (the module, not the names imported from it).
    - Relative imports resolve against the file's package: for module "relay.service.app",
      `from . import x` is "relay.service", `from .directory import x` is
      "relay.service.directory", and `from ..worker import x` is "relay.worker". For a
      package's __init__.py the package is the module itself.
    Sort by line number, keeping source order within a line.
    """
    package = module if is_package else module.rpartition(".")[0]
    out: list[Import] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out += [Import(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = parts[: len(parts) - node.level + 1]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            out.append(Import(node.lineno, target))
    return sorted(out, key=lambda i: i.line)


def build_graph(files: dict[str, str]) -> dict[str, list[Import]]:
    """{module: imports} for every Python module under src/ (provided)."""
    graph = {}
    for path, text in sorted(files.items()):
        mod = module_name(path)
        if mod is not None:
            graph[mod] = imports_of(text, mod, path.endswith("__init__.py"))
    return graph
