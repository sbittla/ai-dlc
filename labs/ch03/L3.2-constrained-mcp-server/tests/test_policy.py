"""Specification tests for the query policy: one rule per test, checkable by hand."""

import json
import sqlite3

import pytest

from relaymcp import policy
from relaymcp.policy import PolicyError, ValidatedRequest
from relaymcp.templates import MAX_LIMIT, MAX_REQUEST_BYTES, TEMPLATES, Param, Template


def code_of(request):
    with pytest.raises(PolicyError) as exc:
        policy.validate_request(request)
    return exc.value.code


# ------------------------------------------------------------ validate_request

def test_valid_request_fills_defaults():
    req = policy.validate_request({"template": "tasks_by_project", "params": {"project_id": 3}})
    assert req == ValidatedRequest("tasks_by_project", {"project_id": 3, "status": None}, 20)


def test_valid_json_text_is_accepted():
    text = json.dumps({"template": "task_by_id", "params": {"task_id": 7}, "limit": 1})
    assert policy.validate_request(text) == ValidatedRequest("task_by_id", {"task_id": 7}, 1)


@pytest.mark.parametrize("request_,code", [
    ("not json", "invalid_json"),
    ("[1, 2]", "invalid_request"),
    ({"template": "task_by_id", "params": {"task_id": 1}, "sql": "x", "columns": "y"}, "unknown_field"),
    ({"template": "drop_everything"}, "unknown_template"),
    ({"template": 7}, "unknown_template"),
    ({"template": "task_by_id", "params": "task_id=1"}, "invalid_request"),
    ({"template": "task_by_id", "params": {"task_id": 1, "z": 1, "a": 2}}, "unknown_param"),
    ({"template": "task_by_id", "params": {}}, "missing_param"),
    ({"template": "task_by_id", "params": {"task_id": "7"}}, "bad_type"),
    ({"template": "task_by_id", "params": {"task_id": True}}, "bad_type"),
    ({"template": "task_by_id", "params": {"task_id": 7.0}}, "bad_type"),
    ({"template": "task_by_id", "params": {"task_id": 0}}, "out_of_range"),
    ({"template": "tasks_by_project", "params": {"project_id": 1, "status": "Open"}}, "bad_value"),
    ({"template": "tasks_by_project", "params": {"project_id": 1, "status": 1}}, "bad_type"),
    ({"template": "overdue_tasks", "params": {"project_id": 1, "as_of": "2026-02-30"}}, "bad_type"),
    ({"template": "overdue_tasks", "params": {"project_id": 1, "as_of": "20261108"}}, "bad_type"),
    ({"template": "search_tasks", "params": {"project_id": 1, "title_contains": "x" * 41}}, "too_long"),
    ({"template": "search_tasks", "params": {"project_id": 1, "title_contains": "tab\there"}}, "bad_value"),
    ({"template": "task_by_id", "params": {"task_id": 1}, "limit": "5"}, "bad_type"),
    ({"template": "task_by_id", "params": {"task_id": 1}, "limit": 0}, "out_of_range"),
    ({"template": "task_by_id", "params": {"task_id": 1}, "limit": MAX_LIMIT + 1}, "limit_exceeded"),
])
def test_each_refusal_code(request_, code):
    assert code_of(request_) == code


def test_unknown_field_and_param_name_the_first_in_sorted_order():
    with pytest.raises(PolicyError, match="unknown field 'columns'"):
        policy.validate_request({"template": "task_by_id", "sql": "x", "columns": "y"})
    with pytest.raises(PolicyError, match="unknown parameter 'a'"):
        policy.validate_request({"template": "task_by_id", "params": {"task_id": 1, "z": 1, "a": 2}})


def test_size_is_checked_before_anything_else():
    big = "x" * (MAX_REQUEST_BYTES + 1)
    assert code_of(big) == "request_too_large"   # not invalid_json
    assert code_of({"template": "nope", "pad": "y" * MAX_REQUEST_BYTES}) == "request_too_large"


def test_limit_at_the_cap_is_allowed():
    req = policy.validate_request({"template": "task_by_id", "params": {"task_id": 1}, "limit": MAX_LIMIT})
    assert req.limit == MAX_LIMIT


# ------------------------------------------------------------ escape_like, redact_row

def test_escape_like_escapes_backslash_first():
    assert policy.escape_like(r"100%_a\b") == r"100\%\_a\\b"
    assert policy.escape_like("plain") == "plain"


def test_redact_row_replaces_pii_and_counts():
    row = {"id": 1, "email": "ana@example.com", "display_name": None, "role": "Owner"}
    clean, n = policy.redact_row(row)
    assert clean == {"id": 1, "email": "[redacted:email]", "display_name": None, "role": "Owner"}
    assert n == 1 and row["email"] == "ana@example.com"  # input untouched


# ------------------------------------------------------------ run_template

def test_run_template_truncates_at_the_limit(conn):
    req = ValidatedRequest("tasks_by_project", {"project_id": 1, "status": None}, 5)
    result = policy.run_template(conn, req)
    assert result.columns == ("id", "title", "status", "due", "assignee_id")
    assert [r["id"] for r in result.rows] == [1, 2, 3, 4, 5] and result.truncated


def test_run_template_not_truncated_when_everything_fits(conn):
    result = policy.run_template(conn, ValidatedRequest("task_by_id", {"task_id": 7}, 20))
    assert len(result.rows) == 1 and not result.truncated


def test_like_parameter_matches_wildcards_literally(conn):
    literal = policy.run_template(conn, ValidatedRequest("search_tasks", {"project_id": 1, "title_contains": "%"}, 50))
    assert literal.rows and all("%" in r["title"] for r in literal.rows)
    unescaped = conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id = 1 AND title LIKE '%%%'").fetchone()[0]
    assert len(literal.rows) < unescaped  # escaping is what stops '%' matching every task


# ------------------------------------------------------------ lint_templates

def test_reference_templates_are_clean():
    assert policy.lint_templates() == []


def test_lint_finds_every_kind_of_problem():
    bad = {
        "a": Template("a", "", "DELETE FROM tasks WHERE id = :id; SELECT 1", {"id": Param("int")}),
        "b": Template("b", "", "SELECT * FROM users WHERE id = ?", {"uid": Param("int")}),
        "c": Template("c", "", "SELECT password_hash, id FROM users JOIN audit_log ON 1 = 1 WHERE id = :x", {}),
    }
    assert policy.lint_templates(bad) == [
        "a: not a single SELECT",
        "b: selects *", "b: string formatting", "b: unused parameter uid",
        "c: undeclared parameter :x", "c: table not allowlisted: audit_log", "c: secret column: password_hash",
    ]


# ------------------------------------------------------------ handle and the audit log

def test_handle_success_shape_and_audit_entry(conn, audit):
    resp = policy.handle({"template": "project_members", "params": {"project_id": 1}, "limit": 2}, conn, audit,
                         caller="agent-7")
    assert resp["ok"] and resp["row_count"] == 2 and resp["truncated"] and resp["redacted_values"] == 4
    assert resp["columns"] == ["id", "display_name", "email", "role", "tz"]
    assert all(r["email"] == "[redacted:email]" for r in resp["rows"])
    (entry,) = audit.entries
    assert entry["caller"] == "agent-7" and entry["outcome"] == "ok" and entry["rows"] == 2
    assert entry["params"] == {"project_id": 1} and entry["at"] == "2026-11-08T09:00:00+00:00"
    assert len(entry["request_sha256"]) == 64


def test_refusals_are_audited_without_the_raw_request(conn, audit):
    raw = '{"template": "users", "params": {"q": "SELECT password_hash FROM users"}}'
    resp = policy.handle(raw, conn, audit)
    assert resp == {"ok": False, "error": "unknown_template", "message": "not an allowlisted template"}
    (entry,) = audit.entries
    assert entry["outcome"] == "unknown_template" and entry["template"] is None and entry["params"] is None
    assert entry["request_bytes"] == len(raw) and "password_hash" not in json.dumps(entry)


def test_sqlite_errors_become_query_failed_without_detail(audit):
    broken = sqlite3.connect(":memory:")  # no tables at all
    resp = policy.handle({"template": "task_by_id", "params": {"task_id": 1}}, broken, audit)
    assert resp == {"ok": False, "error": "query_failed", "message": "the query could not be completed"}
    assert audit.entries[0]["outcome"] == "query_failed" and audit.entries[0]["template"] == "task_by_id"


def test_handle_fails_closed_when_the_audit_log_fails(conn):
    class BrokenAudit:
        def record(self, **fields):
            raise OSError("disk full")
    resp = policy.handle({"template": "task_by_id", "params": {"task_id": 7}}, conn, BrokenAudit())
    assert resp == {"ok": False, "error": "audit_failed", "message": "the call could not be audited"}


def test_audit_log_writes_json_lines(tmp_path, conn):
    log = policy.AuditLog(tmp_path / "audit.jsonl", clock=lambda: "t0")
    policy.handle({"template": "task_by_id", "params": {"task_id": 7}}, conn, log)
    policy.handle("nope", conn, log)
    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["outcome"] for x in lines] == ["ok", "invalid_json"]


def test_every_template_runs(conn):
    samples = {"task_by_id": {"task_id": 7}, "tasks_by_project": {"project_id": 2},
               "overdue_tasks": {"project_id": 2, "as_of": "2026-11-08"},
               "search_tasks": {"project_id": 1, "title_contains": "Fix"},
               "project_members": {"project_id": 3}, "webhook_failures": {"workspace_id": 2, "min_attempts": 2}}
    assert set(samples) == set(TEMPLATES)
    for name, params in samples.items():
        req = policy.validate_request({"template": name, "params": params})
        assert policy.run_template(conn, req).rows, name
