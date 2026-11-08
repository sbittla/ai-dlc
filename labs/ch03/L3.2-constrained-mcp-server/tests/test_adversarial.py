"""Adversarial tests: the request set, and attacks on the connection itself.

The connection tests exercise provided code (db.py), so they pass before you
start: they show what SQLite enforces even if the policy were bypassed.
"""

import json
import sqlite3

import pytest
from conftest import DATA_DIR

from relaymcp import policy

REQUESTS = [json.loads(x) for x in (DATA_DIR / "requests.jsonl").read_text(encoding="utf-8").splitlines() if x]

EXPECTED = {
    "L01": "ok", "L02": "ok", "L03": "ok", "L04": "ok", "L05": "ok", "L06": "ok", "L07": "ok", "L08": "ok",
    "A01": "unknown_template", "A02": "unknown_field", "A03": "unknown_template", "A04": "bad_type",
    "A05": "bad_type", "A06": "bad_value", "A07": "ok", "A08": "ok", "A09": "unknown_param",
    "A10": "limit_exceeded", "A11": "out_of_range", "A12": "request_too_large", "A13": "too_long",
    "A14": "out_of_range", "A15": "bad_type", "A16": "bad_value", "A17": "invalid_json", "A18": "invalid_request",
}


@pytest.mark.parametrize("item", REQUESTS, ids=[r["id"] for r in REQUESTS])
def test_request_set_outcomes(item, conn, audit):
    resp = policy.handle(item["request"], conn, audit)
    assert (resp["error"] if not resp["ok"] else "ok") == EXPECTED[item["id"]]
    assert len(audit.entries) == 1


def test_union_injection_is_bound_as_data_and_returns_nothing(conn, audit):
    item = next(r for r in REQUESTS if r["id"] == "A07")
    resp = policy.handle(item["request"], conn, audit)
    assert resp["ok"] and resp["rows"] == [] and resp["columns"] == ["id", "title", "status", "due"]


# ------------------------------------------------------------ the connection itself (provided code)

@pytest.mark.parametrize("sql", [
    "DELETE FROM tasks",
    "UPDATE tasks SET status = 'done'",
    "INSERT INTO tasks (id, project_id, title, status) VALUES (999, 1, 'x', 'open')",
    "DROP TABLE tasks",
    "CREATE TABLE stolen (x)",
    "ATTACH DATABASE 'other.db' AS other",
    "PRAGMA query_only = OFF",
    "SELECT password_hash FROM users",
    "SELECT api_token_hash FROM users",
    "SELECT name FROM workspaces",
    "SELECT sql FROM sqlite_master",
    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT x FROM n",
])
def test_connection_refuses_writes_and_secrets(conn, sql):
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(sql).fetchall()


def test_connection_aborts_runaway_queries(conn):
    conn.reset_budget()
    with pytest.raises(sqlite3.OperationalError, match="interrupt"):
        conn.execute("SELECT COUNT(*) FROM tasks a, tasks b, tasks c, tasks d").fetchone()
    conn.reset_budget()
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (80,)  # usable again afterwards
