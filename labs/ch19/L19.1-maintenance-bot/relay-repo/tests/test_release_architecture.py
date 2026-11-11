"""relay.release's boundaries (4.29.0): standard library only, no network, no shell, nothing imports the
service, worker or agent runtime."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "relay" / "release"


def imported(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level:
            out.add(node.module or "")
    return out


def test_the_package_has_its_three_modules():
    assert sorted(p.name for p in PKG.glob("*.py")) == ["__init__.py", "flags.py", "judged.py"]


def test_standard_library_only_and_no_network_or_shell():
    mods = set().union(*(imported(p) for p in PKG.glob("*.py")))
    assert {m.split(".")[0] for m in mods} <= set(sys.stdlib_module_names) | {"__future__"}
    assert not {m.split(".")[0] for m in mods} & {"socket", "ssl", "http", "urllib", "subprocess", "os"}
