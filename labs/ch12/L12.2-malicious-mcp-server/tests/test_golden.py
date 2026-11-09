"""Golden tests: every number Chapter 12 quotes from Lab 12.2, and the data's integrity."""

import json
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT, VENDOR
from mcpguard.report import render_calls, render_removeone, render_scenarios

LAB32 = LAB_ROOT.parent.parent / "ch03" / "L3.2-constrained-mcp-server"


def test_scenarios():
    text = render_scenarios()
    assert "Malicious scenarios caught at admission: 8 of 8. Benign S01: admitted in all 3 sessions." in text
    for row in ("| S04 | MCP010 | MCP010 | relay-db-readonly | caught |",
                "| S05 | MCP003, MCP004, MCP010 | MCP003, MCP004, MCP010 | relay-db-readonly | caught |",
                "| S11 | MCP020 | MCP020 | relay-db-readonly | caught |",
                "| S01 | none | none | relay-db-readonly, notes-helper | clean |"):
        assert row in text
    assert "(unexpected)" not in text


def test_remove_one():
    text = render_removeone()
    for row in ("| allowlist | S02, S03 |", "| pin | S04 |", "| shadowing | S11 |", "| scope | S07, S08 |"):
        assert row in text


def test_calls():
    text = render_calls()
    assert "S09: admitted; 3 rows returned, 1 carrying a placeholder marker; result trust: untrusted." in text
    assert "S10: refused by Lab 3.2's policy: unknown_field; result trust: untrusted." in text


def files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def test_generator_reproduces_the_data(tmp_path):
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    assert files(tmp_path) == files(DATA_DIR)
    for rel in files(DATA_DIR):
        assert (tmp_path / rel).read_bytes().replace(b"\r\n", b"\n") == \
            (DATA_DIR / rel).read_bytes().replace(b"\r\n", b"\n"), rel
        assert "GENERATED" in (DATA_DIR / rel).read_text(encoding="utf-8")


def test_the_vendored_server_is_lab_3_2s_solution_unchanged():
    for name in ("__init__.py", "templates.py", "db.py", "policy.py"):
        ours = (VENDOR / "relaymcp" / name).read_bytes().replace(b"\r\n", b"\n")
        theirs = (LAB32 / "solution" / "relaymcp" / name).read_bytes().replace(b"\r\n", b"\n")
        assert ours == theirs, name
    sql = (VENDOR / "relay-test.sql").read_bytes().replace(b"\r\n", b"\n")
    assert sql == (LAB32 / "data" / "relay-test.sql").read_bytes().replace(b"\r\n", b"\n")


def test_reviewed_hash_of_the_vendored_server_is_its_real_source_hash():
    from mcpguard.fixtures import source_sha256
    reviewed = json.loads((DATA_DIR / "reviewed.json").read_text(encoding="utf-8"))["servers"]
    assert reviewed["relay-db-readonly"]["source_sha256"] == source_sha256(VENDOR / "relaymcp")
