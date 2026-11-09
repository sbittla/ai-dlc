"""Checking an agent's claims (prkit.claims.verify_claim): first on a tiny repository you can read in full,
then on canonical Relay 4.21.0 with the simulated agent's eight claims."""

import json

import pytest
from conftest import BASE_REPO, DATA_DIR

from prkit.claims import verify_claim

TINY = {
    "src/relay/a.py": 'SQL = "SELECT * FROM jobs WHERE id = ?"\n\n\ndef load(store):\n    return store.fetch(1)\n',
    "src/relay/b.py": "from .a import load\n\n\ndef use(store):\n    return load(store)\n",
    "src/relay/worker/run.py": "from ..escalation import run_pass\n",
    "src/relay/store.py": 'S = """\nCREATE TABLE IF NOT EXISTS log (\n    id INTEGER,\n'
                          "    kind TEXT NOT NULL CHECK (kind IN ('a', 'b'))\n);\n\"\"\"\n",
    "tests/test_a.py": "def test_x(store):\n    assert store.outbox() == []\n",
    "tests/service_helpers.py": 'M = [("/r", "DELETE", "/r/1", "t", None, 405, "no route")]\n',
    "specs/1/contracts/x-api.openapi.json": json.dumps({"paths": {"/r": {"get": {}, "put": {}, "parameters": []}}}),
}


@pytest.fixture
def tiny(tmp_path):
    for rel, text in TINY.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("claim, holds", [
    ({"kind": "table_users", "table": "jobs", "expect": ["src/relay/a.py"]}, True),
    ({"kind": "table_users", "table": "jobs", "expect": ["src/relay/b.py"]}, False),
    ({"kind": "callers", "function": "load", "scope": "src", "expect": ["src/relay/b.py"]}, True),
    ({"kind": "callers", "function": "fetch", "scope": "src", "expect": []}, False),
    ({"kind": "tests_matching", "pattern": r"outbox\(\) == \[\]", "expect": 1}, True),
    ({"kind": "check_constraint", "table": "log", "column": "kind", "value": "c", "expect": True}, False),
    ({"kind": "check_constraint", "table": "log", "column": "kind", "value": "a", "expect": True}, True),
    ({"kind": "imports", "package": "src/relay/worker", "module": "relay.escalation", "expect": True}, True),
    ({"kind": "openapi_operations", "expect": 2}, True),
    ({"kind": "matrix_row", "method": "DELETE", "status": 405, "expect": True}, True),
])
def test_each_kind_of_claim_on_a_tiny_repository(tiny, claim, holds):
    assert verify_claim(tiny, dict(claim, id="T")).holds is holds


def test_evidence_names_the_file_and_line(tiny):
    claim = {"id": "T", "kind": "callers", "function": "fetch", "scope": "src", "expect": []}
    assert verify_claim(tiny, claim).evidence == ("src/relay/a.py:5",)


def test_an_unknown_kind_is_refused(tiny):
    with pytest.raises(ValueError):
        verify_claim(tiny, {"id": "T", "kind": "vibes"})


def test_the_simulated_agents_eight_claims_on_relay_4_21_0():
    claims = json.loads((DATA_DIR / "agent-claims.json").read_text(encoding="utf-8"))["claims"]
    verdicts = {c["id"]: verify_claim(BASE_REPO, c).holds for c in claims}
    assert verdicts == {"C1": True, "C2": False, "C3": False, "C4": False,
                        "C5": True, "C6": False, "C7": True, "C8": True}
