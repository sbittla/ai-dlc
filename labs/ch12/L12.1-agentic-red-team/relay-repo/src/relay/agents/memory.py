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

From 4.26.0 (ADR-034) both carry trust, because Chapter 12's attacks use them to launder an instruction:

- A message records whether it holds untrusted text (`trust`). A summary that replaces any untrusted
  message is untrusted, whatever the summarizer wrote, so compaction cannot turn a ticket's instruction
  into what looks like the agent's own note. An untrusted message may not be pinned.
- Recall goes through `RECALL_MEMORY`, whose result is untrusted, so a run that recalls memory is tainted.
- A fact proposed from an untrusted source (`source_trust="untrusted"`) is refused if it holds an
  address, a link or an instruction to act, and the refusal is audited. Other untrusted facts may be
  proposed, reviewed and recalled, and recall returns their trust so the run can mark them as data.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from typing import Callable

from .contracts import Param, ToolContract

TRUST = ("trusted", "untrusted")
# What an untrusted fact may not contain: an address, a link, or an instruction to send, forward or copy.
_ACTIONABLE = re.compile(r"https?://|www\.|\b[\w.+-]+@[\w-]+\.[\w.-]+|\b(?:always|never|must|should)\b.{0,40}"
                         r"\b(?:send|forward|copy|cc|bcc|email|post|upload|share|include|attach|call)\b"
                         r"|\b(?:send|forward|copy|cc|bcc|upload)\b.{0,30}\b(?:to|into)\b", re.I)


@dataclass(frozen=True)
class Message:
    role: str
    text: str
    tokens: int
    pinned: bool = False
    trust: str = "trusted"  # 4.26.0: "untrusted" for text an outsider can write (ADR-034)


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
    if any(m.pinned and m.trust != "trusted" for m in messages):
        raise ValueError("an untrusted message cannot be pinned")
    before = sum(m.tokens for m in messages)
    if before <= budget_tokens:
        return Compacted(list(messages), 0, before, before)
    cut = max(0, len(messages) - keep_last)
    old = [m for m in messages[:cut] if not m.pinned]
    if not old:
        raise ValueError("nothing can be compacted without dropping a pinned or recent message")
    summary = summarize(old)
    if any(m.trust != "trusted" for m in old) and summary.trust == "trusted":
        summary = replace(summary, trust="untrusted")  # the summary carries what it summarized
    if summary.pinned:
        summary = replace(summary, pinned=False)
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
    expires_at REAL NOT NULL,
    trust TEXT NOT NULL DEFAULT 'trusted' CHECK (trust IN ('trusted', 'untrusted'))
);
"""


# The contract any agent uses to recall memory (ADR-034). Its result may hold facts first read in untrusted text,
# so a recall taints the run, and the tool-call boundary then refuses any external effect no person approved.
# This is the second, independent control on persistence: if a planted fact passes the pattern check and a
# reviewer, what it asks for is still stopped at the boundary, which is a different module from this one.
RECALL_MEMORY = ToolContract(
    "recall_memory", "Recall accepted facts on one topic, each with its source and trust.",
    (Param("topic", "str", max_len=80),), "read", untrusted_result=True)


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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(agent_memory)")}
        if "trust" not in columns:  # a 4.24.0 table: every fact in it was proposed without trust
            conn.execute("ALTER TABLE agent_memory ADD COLUMN trust TEXT NOT NULL DEFAULT 'trusted'")

    def propose(self, topic: str, fact: str, source: str, run_id: str, agent_id: str, ttl_days: int = 90,
                source_trust: str = "trusted") -> int:
        """An agent proposes a fact it read in `source`. It is stored, not yet retrievable.

        A fact from an untrusted source that holds an address, a link or an instruction to act is refused,
        and the refusal is written to the audit trail when there is one (ADR-034).
        """
        if not source:
            raise MemoryRefused("a fact needs the source it was read from")
        if source_trust not in TRUST:
            raise MemoryRefused(f"unknown trust {source_trust!r}")
        if source_trust == "untrusted" and _ACTIONABLE.search(fact):
            if self.trail is not None:
                self.trail.append(agent_id=agent_id, owner=None, action="memory.propose", resource=f"run:{run_id}",
                                  outcome="refused", source="relay.agents",
                                  detail={"code": "untrusted_instruction", "topic": topic, "source": source})
            raise MemoryRefused("untrusted_instruction")
        cur = self.conn.execute(
            "INSERT INTO agent_memory (topic, fact, source, run_id, proposed_by, status, expires_at, trust)"
            " VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)",
            (topic, fact, source, run_id, agent_id, self.clock() + ttl_days * 86400, source_trust))
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
            "SELECT memory_id, fact, source, run_id, proposed_by, reviewed_by, trust FROM agent_memory"
            " WHERE topic = ? AND status = 'accepted' AND expires_at > ? ORDER BY memory_id",
            (topic, self.clock())).fetchall()
        keys = ("memory_id", "fact", "source", "run_id", "proposed_by", "reviewed_by", "trust")
        return [dict(zip(keys, r)) for r in rows]
