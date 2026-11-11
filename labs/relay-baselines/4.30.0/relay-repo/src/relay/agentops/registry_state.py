"""The agent registry's live state in a shared database (added in 4.30.0; ADR-051).

Chapter 14's `AgentRegistry` keeps each agent's enabled flag and epoch in memory. That is enough for one
process, and not for production: the service, every worker and the monitor are separate processes, so a kill
switch tripped in one is invisible to the others until they restart. Chapter 16's monitor therefore could not
trip a switch automatically, and the service could not verify agent tokens against current state.

`SharedRegistry` keeps the reviewed registry file (`governance/agents.json`) as the source of who each agent
is, and moves the four fields that change at run time into one table, `agent_registry_state`:
`enabled`, `epoch`, `tripped_at` and the current `subject` (a restore under a new role changes it). Every
read goes to the table, with no cache, so a trip in any process is seen by the next verification in every
other process. It is a drop-in for `AgentRegistry`: `TokenService`, `killswitch.trip` and `killswitch.restore`
use it unchanged.

Writes are single `BEGIN IMMEDIATE` transactions, and `disable` increments the epoch in SQL, so two
processes tripping the same agent at once move it on twice rather than losing one trip. The table lives in
Relay's database, which in 4.30.0 is still SQLite; it moves with the PostgreSQL adapter.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from pathlib import Path

from ..audit import AgentIdentity, AgentRegistry

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_registry_state (
    agent_id    TEXT PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1,
    epoch       INTEGER NOT NULL DEFAULT 1,
    tripped_at  REAL,
    subject     TEXT NOT NULL,
    cloud_role  TEXT,
    updated_at  REAL NOT NULL
);
"""


class SharedRegistry(AgentRegistry):
    """The registry file for identities, a shared table for state. Every read sees the latest trip."""

    def __init__(self, data: dict, db_path: str | Path, clock=time.time) -> None:
        super().__init__(data)
        self.clock = clock
        self.conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=5.0)
        if str(db_path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for agent in super().agents():
                self.conn.execute("INSERT OR IGNORE INTO agent_registry_state (agent_id, subject, cloud_role, "
                                  "updated_at) VALUES (?, ?, ?, ?)",
                                  (agent.agent_id, agent.subject, agent.cloud_role, self.clock()))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise

    @classmethod
    def open(cls, registry_path: str | Path, db_path: str | Path, clock=time.time) -> SharedRegistry:
        import json
        return cls(json.loads(Path(registry_path).read_text(encoding="utf-8")), db_path, clock)

    def _live(self, agent: AgentIdentity) -> AgentIdentity:
        row = self.conn.execute("SELECT enabled, epoch, tripped_at, subject, cloud_role FROM agent_registry_state "
                                "WHERE agent_id = ?", (agent.agent_id,)).fetchone()
        if row is None:  # registered after this database was created: starts enabled at epoch 1
            return agent
        return replace(agent, enabled=bool(row[0]), epoch=row[1], tripped_at=row[2], subject=row[3],
                       cloud_role=row[4])

    def get(self, agent_id: str) -> AgentIdentity:
        return self._live(super().get(agent_id))

    def agents(self) -> list[AgentIdentity]:
        return [self._live(a) for a in super().agents()]

    def by_workload(self, issuer: str, subject: str) -> AgentIdentity | None:
        return next((a for a in self.agents() if (a.issuer, a.subject) == (issuer, subject)), None)

    def disable(self, agent_id: str, at: float | None = None) -> AgentIdentity:
        super().get(agent_id)  # KeyError for an agent the registry file does not know
        when = self.clock() if at is None else at
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("UPDATE agent_registry_state SET enabled = 0, epoch = epoch + 1, tripped_at = ?, "
                              "updated_at = ? WHERE agent_id = ?", (when, self.clock(), agent_id))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(agent_id)

    def enable(self, agent_id: str, new_subject: str | None = None,
               new_cloud_role: str | None = None) -> AgentIdentity:
        """Re-enable without resetting the epoch, optionally under a new workload (see `AgentRegistry.enable`)."""
        current = self.get(agent_id)
        subject, role = current.subject, current.cloud_role
        if new_subject is not None:
            if any(o.agent_id != agent_id and (o.issuer, o.subject) == (current.issuer, new_subject)
                   for o in self.agents()):
                raise ValueError("the new subject belongs to another agent")
            subject, role = new_subject, new_cloud_role or current.cloud_role
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute("UPDATE agent_registry_state SET enabled = 1, subject = ?, cloud_role = ?, "
                              "updated_at = ? WHERE agent_id = ?", (subject, role, self.clock(), agent_id))
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        return self.get(agent_id)
