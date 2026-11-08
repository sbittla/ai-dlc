"""The MCP wrapper. Skipped unless the optional extra is installed: pip install -e ".[mcp]"."""

import asyncio
import json

import pytest
from conftest import SQL

pytest.importorskip("mcp.server.mcpserver", reason="optional extra: pip install -e \".[mcp]\"")

from relaymcp.server import build_server  # noqa: E402


def call(server, name, args):
    async def go():
        try:
            return await server.call_tool(name, args)
        except Exception as exc:  # surface a starter TODO as itself, not as an SDK wrapper error
            cause = exc.__cause__
            while cause is not None:
                if isinstance(cause, NotImplementedError):
                    raise cause from None
                cause = cause.__cause__
            raise
    result = asyncio.run(go())
    return json.loads(result.content[0].text)


def test_tools_are_listed_with_read_only_hints():
    server, _ = build_server(SQL)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"list_templates", "query"}
    assert tools["query"].annotations.read_only_hint is True
    assert tools["query"].annotations.destructive_hint is False
    assert tools["query"].input_schema["required"] == ["template"]


def test_query_through_mcp_is_redacted_and_audited(tmp_path):
    server, audit = build_server(SQL, tmp_path / "audit.jsonl")
    resp = call(server, "query", {"template": "project_members", "params": {"project_id": 1}})
    assert resp["ok"] and resp["redacted_values"] == 12
    assert audit.entries[-1]["caller"] == "mcp-stdio"
    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_injection_through_mcp_is_refused_by_the_policy():
    server, audit = build_server(SQL)
    resp = call(server, "query", {"template": "users; DROP TABLE tasks", "params": {}})
    assert resp["error"] == "unknown_template" and audit.entries[-1]["outcome"] == "unknown_template"


def test_sdk_coerces_loose_types_so_the_policy_must_check_its_own():
    # mcp 2.3.0 validates tool arguments in lax mode: "5" and true become ints
    # before the tool runs. Parameters inside `params` reach the policy untouched.
    server, audit = build_server(SQL)
    assert call(server, "query", {"template": "task_by_id", "params": {"task_id": 7}, "limit": "5"})["ok"]
    assert audit.entries[-1]["limit"] == 5
    assert call(server, "query", {"template": "task_by_id", "params": {"task_id": 7}, "limit": True})["ok"]
    assert audit.entries[-1]["limit"] == 1
    resp = call(server, "query", {"template": "task_by_id", "params": {"task_id": "7"}})
    assert resp["error"] == "bad_type"
