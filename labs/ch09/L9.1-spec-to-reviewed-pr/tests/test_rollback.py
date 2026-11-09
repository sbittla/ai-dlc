"""The escalation series' rollback plan (ADR-016, ADR-019), tested with both versions' own code.

Rolling the code back to 4.21.0 leaves the schema at version 2, which 4.21.0 can
open. A rule deleted under 4.22.0 is listed again by 4.21.0's code, but nothing
fires it: 4.21.0's worker runs no evaluation pass. Rolling forward to 4.22.0
finds the rule still deleted. A schema downgrade is possible only before the
first deletion; after it, the plan is to roll forward.

Each step runs in its own interpreter, with one version's src/ on the path.
"""

import json
import os
import subprocess
import sys

import pytest
from conftest import BASE_REPO, RELAY_REPO

SETUP = """
import json, sys
from datetime import datetime, timezone
from relay.escalation import EscalationStore, Rule, Step, delete_rule, rules_for, save_rule
from relay.models import Project, User
at = datetime(2026, 12, 14, 10, 0, tzinfo=timezone.utc)
p = Project(10, "Rotterdam")
users = {1: User(1, "o@x.example", "O", "Owner", "UTC"), 2: User(2, "a@x.example", "A", "Admin", "UTC")}
store = EscalationStore(sys.argv[1])
for rid in ("R-A", "R-B"):
    save_rule(store, Rule(rid, 10, "P1", (Step(1, 10, (2,)),)), users[2], p, users, at)
"""
DELETE = SETUP + """delete_rule(store, "R-A", users[2], p, users, at)
print(json.dumps([r.rule_id for r in rules_for(store, 10)]))
"""
LIST = """
import json, sys
from relay.escalation import EscalationStore, rules_for
print(json.dumps([r.rule_id for r in rules_for(EscalationStore(sys.argv[1]), 10)]))
"""
WORKER = """
import json, sys
import relay.worker
print(json.dumps("relay.escalation" in sys.modules))
"""


def run(src, script, *args):
    out = subprocess.run([sys.executable, "-c", script, *args], capture_output=True, text=True, encoding="utf-8",
                         env=dict(os.environ, PYTHONPATH=str(src), PYTHONDONTWRITEBYTECODE="1"))
    if out.returncode != 0 and "NotImplementedError" in out.stderr:
        raise NotImplementedError("delete_rule is not implemented yet (README step 4)")
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


@pytest.fixture
def v2_db_with_a_deletion(tmp_path):
    path = str(tmp_path / "relay.db")
    assert run(RELAY_REPO / "src", DELETE, path) == ["R-B"]
    return path


def test_4_21_0_opens_a_version_2_database_and_lists_the_deleted_rule_again(v2_db_with_a_deletion):
    assert run(BASE_REPO / "src", LIST, v2_db_with_a_deletion) == ["R-A", "R-B"]


def test_4_21_0_worker_runs_no_evaluation_pass_so_the_resurrected_rule_fires_nothing():
    assert run(BASE_REPO / "src", WORKER) is False


def test_rolling_forward_finds_the_rule_still_deleted(v2_db_with_a_deletion):
    run(BASE_REPO / "src", LIST, v2_db_with_a_deletion)
    assert run(RELAY_REPO / "src", LIST, v2_db_with_a_deletion) == ["R-B"]
