"""A thin MCP server around the policy (provided; optional extra).

    pip install -e ".[mcp]"          # the official MCP Python SDK, pinned to mcp==2.3.0
    python -m relaymcp.server --db ../data/relay-test.sql --audit ../evidence/mcp-audit.jsonl

It speaks MCP over stdio, so an MCP client starts it as a subprocess (see the
`.mcp.json` entry in Lab 3.1's relay-repo). Everything that matters happens in
policy.handle(); this file only translates between MCP and the policy.

Written against mcp 2.3.0, where the high-level server class is
`mcp.server.mcpserver.MCPServer` (it was `FastMCP` in the 1.x SDK) and tool
annotations come from `mcp_types`. Re-check both names if you change the pin.
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from .db import open_readonly
from .policy import AuditLog, handle
from .templates import DEFAULT_LIMIT, MAX_LIMIT, TEMPLATES

# Hints for the client. They describe the tool; they enforce nothing. The
# enforcement is the policy and the read-only connection.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

INSTRUCTIONS = (
    "Read-only access to Relay's synthetic test database through fixed query templates. "
    "Call list_templates first. There is no free-form SQL. Email addresses and names are redacted."
)


def template_catalogue() -> dict:
    return {"default_limit": DEFAULT_LIMIT, "max_limit": MAX_LIMIT, "templates": [
        {"name": t.name, "description": t.description,
         "params": {n: {"type": p.type, "required": p.required, **({"choices": list(p.choices)} if p.choices else {}),
                        **({"min": p.min, "max": p.max} if p.type == "int" else {}),
                        **({"max_len": p.max_len} if p.max_len else {})} for n, p in t.params.items()}}
        for t in TEMPLATES.values()]}


def build_server(sql_path: Path, audit_path: Path | None = None, caller: str = "mcp-stdio") -> tuple[MCPServer, AuditLog]:
    conn = open_readonly(sql_path)
    audit = AuditLog(audit_path)
    lock = threading.Lock()  # one SQLite connection, shared by worker threads
    server = MCPServer("relay-db-readonly", instructions=INSTRUCTIONS, version="1.0.0")

    @server.tool(annotations=READ_ONLY)
    def list_templates() -> dict:
        """List the allowlisted query templates and their parameters."""
        return template_catalogue()

    @server.tool(annotations=READ_ONLY)
    def query(template: str, params: dict[str, Any] | None = None, limit: int | None = None) -> dict:
        """Run one allowlisted, read-only query template with typed parameters.

        Returns {"ok": true, "rows": [...], "truncated": ...} or {"ok": false, "error": <code>}.
        """
        request: dict[str, Any] = {"template": template, "params": params if params is not None else {}}
        if limit is not None:
            request["limit"] = limit
        with lock:
            return handle(request, conn, audit, caller=caller)

    return server, audit


def main() -> None:
    ap = argparse.ArgumentParser(description="Relay's constrained, read-only MCP query server (stdio)")
    ap.add_argument("--db", type=Path, required=True, help="the SQL dump to load, e.g. ../data/relay-test.sql")
    ap.add_argument("--audit", type=Path, default=None, help="append audit entries to this JSON-lines file")
    args = ap.parse_args()
    server, _ = build_server(args.db, args.audit)
    server.run()  # stdio; never print to stdout here, it carries the protocol


if __name__ == "__main__":
    main()
