"""The MCP wrapper. Skipped unless the optional extra is installed: pip install -e ".[mcp]"."""

import asyncio
import json

import pytest
from conftest import SQL

pytest.importorskip("mcp.server.mcpserver", reason="optional extra: pip install -e \".[mcp]\"")

from mcp.server.mcpserver import MCPServer  # noqa: E402

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


@pytest.fixture
def served(tmp_path):
    return build_server(SQL, tmp_path / "audit.jsonl")


def test_tools_are_listed_with_read_only_hints(served):
    server, _ = served
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert set(tools) == {"list_templates", "query"}
    assert tools["query"].annotations.read_only_hint is True
    assert tools["query"].annotations.destructive_hint is False
    assert list(tools["query"].input_schema["properties"]) == ["request"]


def test_query_through_mcp_is_redacted_and_audited_to_file(served, tmp_path):
    server, audit = served
    resp = call(server, "query", {"request": {"template": "project_members", "params": {"project_id": 1}}})
    assert resp["ok"] and resp["redacted_values"] == 12
    assert audit.entries[-1]["caller"] == "mcp-stdio"
    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.parametrize("request_,code", [
    ({"template": "users; DROP TABLE tasks", "params": {}}, "unknown_template"),
    ({"template": "task_by_id", "params": "x"}, "invalid_request"),
    ({"template": "task_by_id", "params": {"task_id": 7}, "sql": "SELECT * FROM users"}, "unknown_field"),
    ({"template": "task_by_id", "params": {"task_id": 7}, "limit": "5"}, "bad_type"),
    ({"template": "task_by_id", "params": {"task_id": True}}, "bad_type"),
    (None, "invalid_request"),
])
def test_every_value_inside_the_request_reaches_the_policy_and_is_audited(served, request_, code):
    server, audit = served
    args = {} if request_ is None else {"request": request_}
    assert call(server, "query", args)["error"] == code
    assert audit.entries[-1]["outcome"] == code and len(audit.entries) == 1


def test_arguments_beside_request_are_dropped_by_the_sdk_before_the_tool_runs(served):
    # mcp 2.3.0 ignores undeclared tool arguments. They never reach the policy or the
    # audit log; only `request` does. Chapter 3 states this limit.
    server, audit = served
    resp = call(server, "query", {"request": {"template": "task_by_id", "params": {"task_id": 7}},
                                  "sql": "SELECT * FROM users"})
    assert resp["ok"] and audit.entries[-1]["outcome"] == "ok"


def test_sdk_coerces_typed_arguments_in_lax_mode():
    # Why the server takes one untyped argument: with a typed signature, mcp 2.3.0
    # converts "5" and true to integers before the function runs.
    probe = MCPServer("probe")

    @probe.tool()
    def typed(limit: int = 20) -> dict:
        return {"limit": limit, "type": type(limit).__name__}

    assert call(probe, "typed", {"limit": "5"}) == {"limit": 5, "type": "int"}
    assert call(probe, "typed", {"limit": True}) == {"limit": 1, "type": "int"}


def test_audit_file_is_required():
    import sys

    from relaymcp import server as srv
    argv = sys.argv
    sys.argv = ["relaymcp.server", "--db", str(SQL)]
    try:
        with pytest.raises(SystemExit):
            srv.main()
    finally:
        sys.argv = argv

