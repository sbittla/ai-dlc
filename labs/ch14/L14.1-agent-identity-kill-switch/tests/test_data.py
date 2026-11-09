"""The data is reproducible, labelled as generated, and consistent with Relay 4.23.0's own files."""

import json
import re
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, RELAY

from relay.audit import AgentRegistry


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_json_file_says_it_was_generated():
    for path in sorted(DATA_DIR.rglob("*.json")):
        assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"].upper(), path.name
    assert (DATA_DIR / "incident" / "debug-log-excerpt.txt").read_text(encoding="utf-8").startswith("# FAKE")


def test_every_activity_line_has_a_truth_label_and_the_documented_fields():
    for path in [DATA_DIR / "activity" / "replay-2026-10-26_2026-12-14.jsonl",
                 *sorted((DATA_DIR / "activity" / "seeded").glob("*.jsonl"))]:
        for line in path.read_text(encoding="utf-8").splitlines():
            assert set(json.loads(line)) == {"at", "identity", "agent_id", "on_behalf_of", "action", "resource", "rows",
                                             "source", "outcome", "truth"}


def test_the_after_inventory_matches_the_registry_and_infra():
    registry = AgentRegistry.load(RELAY / "governance" / "agents.json")
    inv = json.loads((DATA_DIR / "identities" / "inventory-2027-01-12.json").read_text(encoding="utf-8"))
    relay_agents = {c["agent"] for c in inv["credentials"] if c["system"] == "relay"}
    assert relay_agents == {a.agent_id for a in registry.agents()}
    for c in inv["credentials"]:
        if c["system"] == "relay":
            assert c["trust_subject"] == registry.get(c["agent"]).subject
            assert set(c["grants"]) == registry.get(c["agent"]).scopes
    tf = "".join(p.read_text(encoding="utf-8") for p in (RELAY / "infra").glob("*.tf"))
    for a in registry.agents():
        if a.cloud_role:
            role = a.cloud_role.rsplit("/", 1)[1].replace("relay-nonprod-", "${local.name}-")
            assert f'name                 = "{role}"' in tf, role


def test_the_vendored_query_tool_is_lab_3_2_unchanged():
    names = sorted(p.name for p in (LAB_ROOT / "vendor" / "relaymcp").glob("*.py"))
    assert names == ["__init__.py", "db.py", "policy.py", "templates.py"]
    sql = (LAB_ROOT / "vendor" / "relay-test.sql").read_text(encoding="utf-8")
    assert len(re.findall(r"INSERT INTO tasks", sql)) == 80


def test_no_real_looking_secret_outside_the_labelled_fake():
    pattern = re.compile(r"rly_(live|test)_[0-9a-f]{32}")
    for path in sorted(DATA_DIR.rglob("*")):
        if path.is_file():
            hits = set(m.group(0) for m in pattern.finditer(path.read_text(encoding="utf-8")))
            assert hits <= {"rly_live_0f1e2d3c4b5a69788796a5b4c3d2e1f0"}, path.name
