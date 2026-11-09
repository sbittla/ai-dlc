"""Caller scoping and a cross-call row budget for Lab 3.2's query tool (starter: TODOs).

Lab 3.2's policy bounds each call: allowlisted templates, typed parameters, 50 rows at most, redaction,
an audit entry. It does not know who is calling, so every caller can read every workspace, and an agent
that calls it 200 times reads 200 calls' worth of rows. Chapter 3 left both gaps to this chapter.

ScopedTool closes them without changing Lab 3.2's code. The caller is the verified Relay agent token's
claims, not anything in the request. The token must carry `testdb:query`; the registry's tool limits
name the workspaces the agent may read and its rows per hour; every call is resolved to a workspace
before it runs, and the budget is shared across calls by the same agent acting for the same person.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from relay.audit import AgentRegistry
from relaymcp.policy import AuditLog, PolicyError, ValidatedRequest, handle, validate_request

TOOL = "relay-db-readonly"
WINDOW = timedelta(hours=1)


def workspace_of(conn: sqlite3.Connection, req: ValidatedRequest) -> int | None:
    """The workspace a validated request reads (provided), or None if it cannot be resolved.

    workspace_id is used as given; project_id and task_id are looked up. The lookups run through the
    same read-only connection and authorizer as the templates.
    """
    if hasattr(conn, "reset_budget"):
        conn.reset_budget()
    p = req.params
    if p.get("workspace_id") is not None:
        return p["workspace_id"]
    if p.get("project_id") is not None:
        row = conn.execute("SELECT workspace_id FROM projects WHERE id = :id", {"id": p["project_id"]}).fetchone()
        return row[0] if row else None
    if p.get("task_id") is not None:
        row = conn.execute("SELECT projects.workspace_id FROM tasks JOIN projects ON projects.id = tasks.project_id "
                           "WHERE tasks.id = :id", {"id": p["task_id"]}).fetchone()
        return row[0] if row else None
    return None


@dataclass
class ScopedTool:
    conn: sqlite3.Connection
    registry: AgentRegistry
    audit: AuditLog
    used: dict = field(default_factory=lambda: defaultdict(deque))  # (agent, person) -> deque[(at, rows)]

    def remaining(self, key: tuple[str, str], budget: int, now: datetime) -> int:
        q = self.used[key]
        while q and q[0][0] <= now - WINDOW:
            q.popleft()
        return budget - sum(rows for _, rows in q)

    def refuse(self, claims: dict, code: str, message: str) -> dict:
        self.audit.record(caller=f"{claims.get('sub')} for {claims.get('obo')}", outcome=code, rows=0)
        return {"ok": False, "error": code, "message": message}

    def handle(self, request: dict, claims: dict, now: datetime) -> dict:
        """Serve one request for the caller in `claims` (already verified by TokenService.verify).

        Checks, in order; each refusal is audited and returned as {"ok": False, "error": code, "message": ...}:
        1. "testdb:query" not in claims["scp"]                          -> "scope_missing"
        2. the agent has no tool_limits entry for TOOL                   -> "no_tool_limits" (fail closed)
        3. validate_request raises PolicyError                           -> its code
        4. workspace_of(...) is None or not in the limits' workspaces    -> "out_of_scope"
        5. remaining(...) <= 0 for key (claims["sub"], claims["obo"])     -> "row_budget_exhausted"
        Otherwise call Lab 3.2's `handle` with the request's limit lowered to min(limit, remaining) and
        caller "<sub> for <obo>", record the rows it returned against the budget at `now`, and return its
        response with "budget_remaining" added (the remaining rows after this call).
        """
        raise NotImplementedError("TODO 6: caller scoping and the row budget")
