"""The audit trail of agent actions: append-only, hash-chained, redacted (added in 4.23.0; ADR-021).

One record per action an agent identity takes through Relay: who (the agent, its accountable
owner, the person it acted for, the credential it used), what (action, resource, outcome), from
where (a network label), and when. Request and response bodies are never recorded; `detail` holds
small structured facts, such as a row count, and is redacted before it is written.

Each record carries the hash of the one before it, so editing or deleting a record breaks the
chain at that point. A chain alone cannot show that its newest records were cut off, so the latest
hash is also copied to a separate, write-once store at intervals (an anchor) and `verify` checks
the chain against it. Where the anchor lives, and who can write there, is an operational decision
in ADR-021; this module only computes and checks.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .redact import redact_value

GENESIS = "0" * 64
BODY_FIELDS = ("seq", "at", "agent_id", "owner", "on_behalf_of", "credential", "action", "resource", "outcome",
               "source", "detail", "prev")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def record_hash(body: dict) -> str:
    """SHA-256 over the canonical JSON of the record's body fields (everything except `hash`)."""
    return hashlib.sha256(canonical({k: body.get(k) for k in BODY_FIELDS})).hexdigest()


@dataclass(frozen=True)
class Verification:
    ok: bool
    checked: int
    seq: int | None = None      # the first record that fails, if any
    problem: str | None = None  # "sequence gap", "broken link", "hash mismatch", "anchor mismatch", ...


def verify(records: list[dict], anchor: tuple[int, str] | None = None) -> Verification:
    """Check the chain from the first record, and optionally against an anchor (seq, hash).

    Problems, in the order they are checked for each record: a `seq` that is not the previous
    one plus 1 (the first must be 1) is "sequence gap"; a `prev` that is not the previous
    record's hash (GENESIS for the first) is "broken link"; a stored hash that does not match
    the recomputed one is "hash mismatch". After the chain, an anchor whose seq is beyond the
    last record is "truncated after anchor", and one whose hash differs is "anchor mismatch".
    """
    prev, expected = GENESIS, 1
    by_seq: dict[int, str] = {}
    for n, rec in enumerate(records):
        seq = rec.get("seq")
        if seq != expected:
            return Verification(False, n, seq, "sequence gap")
        if rec.get("prev") != prev:
            return Verification(False, n, seq, "broken link")
        if rec.get("hash") != record_hash(rec):
            return Verification(False, n, seq, "hash mismatch")
        prev, expected = rec["hash"], expected + 1
        by_seq[seq] = rec["hash"]
    if anchor is not None:
        a_seq, a_hash = anchor
        if a_seq not in by_seq:
            return Verification(False, len(records), a_seq, "truncated after anchor")
        if by_seq[a_seq] != a_hash:
            return Verification(False, len(records), a_seq, "anchor mismatch")
    return Verification(True, len(records))


class AuditTrail:
    """Append-only records, in memory and optionally as JSON lines in a file.

    Opening an existing file continues its chain. Writing to the file happens before the record
    is accepted in memory, so a write that fails leaves nothing half-recorded.
    """

    def __init__(self, path: Path | None = None, clock: Callable[[], str] = utc_now) -> None:
        self.path = Path(path) if path else None
        self.clock = clock
        self.records: list[dict] = []
        self.redactions: Counter = Counter()
        if self.path and self.path.exists():
            self.records = load(self.path)

    @property
    def head(self) -> tuple[int, str]:
        """(seq, hash) of the newest record: the value to copy to the anchor store."""
        if not self.records:
            return 0, GENESIS
        return self.records[-1]["seq"], self.records[-1]["hash"]

    def append(self, *, agent_id: str | None, owner: str | None, action: str, resource: str, outcome: str,
               on_behalf_of: str | None = None, credential: str | None = None, source: str | None = None,
               detail: dict | None = None, at: str | None = None) -> dict:
        seq, prev = self.head
        body = {"seq": seq + 1, "at": at or self.clock(), "agent_id": agent_id, "owner": owner,
                "on_behalf_of": on_behalf_of, "credential": credential, "action": action,
                "resource": redact_value(resource, self.redactions), "outcome": outcome, "source": source,
                "detail": redact_value(detail or {}, self.redactions), "prev": prev}
        record = {**body, "hash": record_hash(body)}
        if self.path:
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        self.records.append(record)
        return record


def load(path: Path) -> list[dict]:
    """Read a JSON-lines trail. Blank lines are ignored; anything else must parse."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
