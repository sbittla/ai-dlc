"""Policy checks derived from the spec's security constraints and data rules.

Spec: ESC-SPEC-1
Spec version: 1.1.0

These read the code and the spec, not the behaviour. They catch a constraint
broken in the obvious way (a new import, a new field, a Task passed to a
renderer); they cannot prove the constraint holds.
"""

import ast
import hashlib
import hmac
import inspect
import json
import re
from pathlib import Path

from escalation_fixtures import ROTTERDAM, SCHEMA, SPEC_DIR, TASK, USERS, default_rule, minutes

from relay.escalation import EngineConfig, EscalationStore, Webhook, delivery, run_pass, save_rule, set_priority

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "relay" / "escalation"
ALLOWED_IMPORTS = {"__future__", "collections.abc", "dataclasses", "datetime", "hashlib", "hmac", "json", "re",
                   "typing"}
STORE_ONLY = {"sqlite3"}  # SEC-05: only store.py and (spec 1.2.0) migrations.py may touch the database
SECRET = b"whsec-test-only-0001"


def data_rules():
    """{field: classification} from the spec's Data rules table."""
    text = (SPEC_DIR / "spec.md").read_text(encoding="utf-8")
    section = text.split("\n## Data rules", 1)[1].split("\n## ", 1)[0]
    rows = [line.strip().strip("|").split("|") for line in section.splitlines() if line.startswith("| `")]
    if not rows:
        raise NotImplementedError("the spec's Data rules table is empty")
    return {cells[0].strip().strip("`"): cells[1].strip() for cells in rows}


def outbound_documents():
    text = (SPEC_DIR / "spec.md").read_text(encoding="utf-8")
    return [name.strip() for name in re.search(r"^Outbound: (.+)$", text, re.M).group(1).split(",")]


def test_SEC03_evaluator_never_reads_suggestions():
    tree = ast.parse((PACKAGE / "evaluate.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not {n for n in names if n.startswith("suggested")}


def test_SEC04_documents_for_delivery_carry_only_internal_or_public_fields():
    rules = data_rules()
    assert rules["Task.title"] == "Confidential"
    assert outbound_documents() == ["Evaluation", "StepDecision", "EmailMessage", "WebhookEvent"]
    for name in outbound_documents():
        for field in SCHEMA["$defs"][name]["properties"]:
            assert rules[f"{name}.{field}"] in ("Public", "Internal"), f"{name}.{field}"


def test_SEC04_no_message_builder_receives_a_task():
    for name, fn in inspect.getmembers(delivery, inspect.isfunction):
        if fn.__module__ != delivery.__name__:
            continue
        annotations = " ".join(str(p.annotation) for p in inspect.signature(fn).parameters.values())
        params = set(inspect.signature(fn).parameters)
        assert "Task" not in annotations and "task" not in params and "title" not in params, name


def test_SEC05_escalation_package_imports_nothing_that_reaches_the_network():
    found, store_only = set(), {}
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            for name in names:
                if name in STORE_ONLY:
                    store_only.setdefault(name, set()).add(path.name)
                else:
                    found.add(name)
    assert found <= ALLOWED_IMPORTS, sorted(found - ALLOWED_IMPORTS)
    assert store_only == {"sqlite3": {"store.py", "migrations.py"}}
    assert not re.search(r"\b(open|exec|eval|__import__)\(", "".join(
        p.read_text(encoding="utf-8") for p in PACKAGE.glob("*.py")))


def _fire_one_step(webhook):
    store = EscalationStore()
    save_rule(store, default_rule(), USERS[2], ROTTERDAM, USERS, minutes(-60))
    set_priority(store, TASK, ROTTERDAM, USERS[4], "P1", minutes(0))
    config = EngineConfig("https://relay.example/ws-demo", webhook)
    run_pass(store, {TASK.id: TASK}, {ROTTERDAM.id: ROTTERDAM}, config, minutes(10))
    return store


def test_SEC06_events_are_signed_over_the_exact_body_and_the_secret_is_never_stored():
    store = _fire_one_step(Webhook("https://hooks.customer.example/relay", SECRET))
    events = [item for item in store.outbox() if item.channel == "webhook"]
    assert len(events) == 1
    expected = "sha256=" + hmac.new(SECRET, events[0].body.encode("utf-8"), hashlib.sha256).hexdigest()
    assert events[0].headers["X-Relay-Signature"] == expected
    dump = json.dumps([item.__dict__ for item in store.outbox()], default=str)
    assert SECRET.decode() not in dump and SECRET.hex() not in dump


def test_ESC_AC31_the_engine_writes_only_email_and_webhook_messages():
    store = _fire_one_step(Webhook("https://hooks.customer.example/relay", SECRET))
    assert {item.channel for item in store.outbox()} == {"email", "webhook"}
    schema = (PACKAGE / "store.py").read_text(encoding="utf-8")
    assert "CHECK (channel IN ('email', 'webhook'))" in schema
