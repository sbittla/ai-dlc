"""Policy checks derived from the spec's security constraints and data rules.

Spec: ESC-SPEC-1
Spec version: 1.0.0

These read the code and the spec, not the behaviour. They catch a constraint
broken in the obvious way (a new import, a new field); they cannot prove the
constraint holds.
"""

import ast
import re
from pathlib import Path

from escalation_fixtures import SCHEMA, SPEC_DIR

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "relay" / "escalation"
OUTBOUND_DOCUMENTS = ("Evaluation", "StepDecision")  # consumed by email and webhook delivery
ALLOWED_IMPORTS = {"__future__", "collections.abc", "dataclasses", "datetime", "re", "typing"}


def data_rules():
    """{field: classification} from the spec's Data rules table."""
    text = (SPEC_DIR / "spec.md").read_text(encoding="utf-8")
    section = text.split("\n## Data rules", 1)[1].split("\n## ", 1)[0]
    rows = [line.strip().strip("|").split("|") for line in section.splitlines() if line.startswith("| `")]
    if not rows:
        raise NotImplementedError("the spec's Data rules table is empty: complete it (Lab 5.1, step 3)")
    return {cells[0].strip().strip("`"): cells[1].strip() for cells in rows}


def test_SEC03_evaluator_never_reads_suggestions():
    tree = ast.parse((PACKAGE / "evaluate.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not {n for n in names if n.startswith("suggested")}


def test_SEC04_documents_for_delivery_carry_only_internal_or_public_fields():
    rules = data_rules()
    assert rules["Task.title"] == "Confidential"
    for name in OUTBOUND_DOCUMENTS:
        for field in SCHEMA["$defs"][name]["properties"]:
            assert rules[f"{name}.{field}"] in ("Public", "Internal"), f"{name}.{field}"


def test_SEC05_escalation_package_imports_nothing_that_reaches_the_network():
    found = set()
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                found.add(node.module)
    assert found <= ALLOWED_IMPORTS, sorted(found - ALLOWED_IMPORTS)
    assert not re.search(r"\b(open|exec|eval|__import__)\(", "".join(
        p.read_text(encoding="utf-8") for p in PACKAGE.glob("*.py")))
