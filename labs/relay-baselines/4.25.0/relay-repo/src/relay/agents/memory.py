"""Compaction of an agent's context, and long-term memory with provenance (added in 4.24.0; ADR-026).

Chapter 2 defined both and named their failure: a summary can drop the fact that mattered, and a memory
can be wrong or planted. These two pieces are built around that failure.

`compact` replaces the oldest messages of a context with one summary, until the context fits its token
budget. Pinned messages (the task, its constraints, the stop rules) are never summarized away, whatever
their age, and the result records what was dropped, so a reviewer can see it.

`MemoryStore` keeps facts that should outlive a run, such as "rules.py's validate_rule takes a project
ID". Every fact records where it came from: the run, the agent, and the source it was read from. An
agent may only propose a fact. A proposed fact is never retrieved; a person must review it first. A fact
can expire, and retrieval returns its provenance with it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Message:
    role: str
    text: str
    tokens: int
    pinned: bool = False


@dataclass(frozen=True)
class Compacted:
    messages: list
    dropped: int
    tokens_before: int
    tokens_after: int


def compact(messages: list[Message], budget_tokens: int, keep_last: int,
            summarize: Callable[[list[Message]], Message]) -> Compacted:
    """Fit `messages` into `budget_tokens`, keeping every pinned message and the last `keep_last` messages.

    The unpinned messages before the last `keep_last` are replaced by one summary (from `summarize`),
    placed where the first of them was. If the context already fits, nothing changes. If it still does
    not fit after compaction, raise ValueError: the run should stop rather than lose a pinned message.
    """
    before = sum(m.tokens for m in messages)
    if before <= budget_tokens:
        return Compacted(list(messages), 0, before, before)
    cut = max(0, len(messages) - keep_last)
    old = [m for m in messages[:cut] if not m.pinned]
    if not old:
        raise ValueError("nothing can be compacted without dropping a pinned or recent message")
    summary = summarize(old)
    out, placed = [], False
    for m in messages[:cut]:
        if m.pinned:
            out.append(m)
        elif not placed:
            out.append(summary)
            placed = True
    out += messages[cut:]
    after = sum(m.tokens for m in out)
    if after > budget_tokens:
        raise ValueError(f"context still needs {after} tokens after compaction; budget is {budget_tokens}")
    return Compacted(out, len(old), before, after)


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_memory (
    memory_id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL,
    fact TEXT NOT NULL,
    source TEXT NOT NULL,
    run_id TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'accepted', 'rejected')),
    reviewed_by TEXT,
    expires_at REAL NOT NULL
);
"""


class MemoryRefused(Exception):
    pass


class MemoryStore:
    def __init__(self, conn: sqlite3.Connection, people: frozenset[str], clock: Callable[[], float],
                 trail=None) -> None:
        self.conn = conn
        self.people = people
        self.clock = clock
        self.trail = trail
        conn.executescript(SCHEMA)

    def propose(self, topic: str, fact: str, source: str, run_id: str, agent_id: str, ttl_days: int = 90) -> int:
        """An agent proposes a fact it read in `source`. It is stored, not yet retrievable."""
        if not source:
            raise MemoryRefused("a fact needs the source it was read from")
        cur = self.conn.execute(
            "INSERT INTO agent_memory (topic, fact, source, run_id, proposed_by, status, expires_at)"
            " VALUES (?, ?, ?, ?, ?, 'proposed', ?)",
            (topic, fact, source, run_id, agent_id, self.clock() + ttl_days * 86400))
        return cur.lastrowid

    def review(self, memory_id: int, person: str, accept: bool) -> None:
        """Accept or reject a proposed fact, once. The review is written to the audit trail when there is one."""
        if person not in self.people:
            raise MemoryRefused("only a person may review a memory")
        row = self.conn.execute("SELECT status, proposed_by, run_id FROM agent_memory WHERE memory_id = ?",
                                (memory_id,)).fetchone()
        if row is None:
            raise MemoryRefused("no such memory")
        if row[0] != "proposed":
            raise MemoryRefused("already reviewed")
        status = "accepted" if accept else "rejected"
        self.conn.execute("UPDATE agent_memory SET status = ?, reviewed_by = ? WHERE memory_id = ?",
                          (status, person, memory_id))
        if self.trail is not None:
            self.trail.append(agent_id=row[1], owner=None, action="memory.review", resource=f"run:{row[2]}",
                              outcome=status, source="relay.agents",
                              detail={"memory_id": memory_id, "reviewed_by": person})

    def recall(self, topic: str) -> list[dict]:
        """Accepted, unexpired facts on `topic`, each with its provenance."""
        rows = self.conn.execute(
            "SELECT memory_id, fact, source, run_id, proposed_by, reviewed_by FROM agent_memory"
            " WHERE topic = ? AND status = 'accepted' AND expires_at > ? ORDER BY memory_id",
            (topic, self.clock())).fetchall()
        keys = ("memory_id", "fact", "source", "run_id", "proposed_by", "reviewed_by")
        return [dict(zip(keys, r)) for r in rows]
