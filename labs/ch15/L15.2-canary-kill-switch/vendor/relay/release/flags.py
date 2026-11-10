"""Feature flags and kill switches for AI features (4.29.0; ADR-047).

Two sources decide whether a feature is on for a workspace:

- the flag document, `deploy/flags.json` (relay-flags-v1), reviewed and versioned like code. It sets each
  feature's rollout percentage. Changing it is a release, so it moves at the pipeline's pace;
- the kill store, a table the service and worker read on every decision. Tripping a kill switch is one row,
  so it takes effect at the next decision, without a release or a rollback.

The rules fail closed:

- an unknown feature is off;
- an AI feature whose entry is malformed is off (and so is every feature, if the document is malformed);
- a tripped kill switch beats every rollout setting;
- a workspace is in a rollout by a stable hash of the feature and the workspace, so the same workspace stays
  in as the percentage grows.

Anyone on the people list, or automation named `automation:<rule>`, may trip a switch. Only a person may
restore one, never the automation that tripped it, and the restore needs a reason that names a ticket or an
incident. Every trip, restore and refusal is written to the log table.

This is distinct from Chapter 14's kill switch for an agent (`relay.audit.killswitch`), which revokes an
identity; this one turns a product feature off for everyone.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass

POLICY = "relay-flags-v1"
_REASON = re.compile(r"^(INC|RLY)-\d+: .{20,}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_kills (
    feature TEXT PRIMARY KEY,
    tripped_at TEXT NOT NULL,
    tripped_by TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feature_kill_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    feature TEXT NOT NULL,
    actor TEXT NOT NULL,
    outcome TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


class FlagError(ValueError):
    """A kill-switch action was refused. The refusal is already in the log."""


def bucket(feature: str, unit: str) -> int:
    """0 to 99, stable for a (feature, workspace) pair."""
    digest = hashlib.sha256(f"{feature}:{unit}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 100


class KillStore:
    """The kill switches, in one table. `people` are the persons allowed to restore."""

    def __init__(self, db: sqlite3.Connection, people: frozenset[str]):
        self.db, self.people = db, frozenset(people)
        self.db.executescript(SCHEMA)

    def _log(self, at: str, action: str, feature: str, actor: str, outcome: str, detail: str) -> None:
        self.db.execute("INSERT INTO feature_kill_log (at, action, feature, actor, outcome, detail) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (at, action, feature, actor, outcome, detail))
        self.db.commit()

    def killed(self, feature: str) -> bool:
        return self.db.execute("SELECT 1 FROM feature_kills WHERE feature = ?", (feature,)).fetchone() is not None

    def trip(self, feature: str, actor: str, reason: str, at: str) -> None:
        """Turn `feature` off now. Persons on the list and `automation:<rule>` may trip; a trip is never refused
        for being a duplicate, because turning something off twice is safe."""
        if actor not in self.people and not re.fullmatch(r"automation:[a-z0-9-]+", actor):
            self._log(at, "trip", feature, actor, "refused", "unknown actor")
            raise FlagError(f"{actor} may not trip a kill switch")
        if not reason.strip():
            self._log(at, "trip", feature, actor, "refused", "no reason")
            raise FlagError("a trip needs a reason")
        self.db.execute("INSERT OR IGNORE INTO feature_kills VALUES (?, ?, ?, ?)", (feature, at, actor, reason))
        self._log(at, "trip", feature, actor, "done", reason)

    def restore(self, feature: str, actor: str, reason: str, at: str) -> None:
        """Turn the kill switch off. Only a person may restore, with a reason `INC-n: …` or `RLY-n: …` of at
        least 20 characters after the prefix."""
        if actor not in self.people:
            self._log(at, "restore", feature, actor, "refused", "only a person may restore")
            raise FlagError(f"{actor} may not restore a kill switch")
        if not _REASON.match(reason):
            self._log(at, "restore", feature, actor, "refused", "reason must name INC-n or RLY-n")
            raise FlagError("a restore needs a reason that names a ticket or an incident")
        if not self.killed(feature):
            self._log(at, "restore", feature, actor, "refused", "not tripped")
            raise FlagError(f"{feature} is not tripped")
        self.db.execute("DELETE FROM feature_kills WHERE feature = ?", (feature,))
        self._log(at, "restore", feature, actor, "done", reason)

    def log(self) -> list[dict]:
        rows = self.db.execute("SELECT at, action, feature, actor, outcome, detail FROM feature_kill_log "
                               "ORDER BY seq").fetchall()
        return [dict(zip(("at", "action", "feature", "actor", "outcome", "detail"), r)) for r in rows]


@dataclass
class FlagSet:
    """The flag document plus the kill store. `enabled` is the only question callers ask."""

    document: dict
    kills: KillStore | None = None

    def _entry(self, feature: str) -> dict | None:
        doc = self.document
        if not isinstance(doc, dict) or doc.get("policy") != POLICY or not isinstance(doc.get("features"), dict):
            return None
        entry = doc["features"].get(feature)
        if not isinstance(entry, dict):
            return None
        pct = entry.get("rollout_percent")
        if not isinstance(pct, int) or isinstance(pct, bool) or not 0 <= pct <= 100:
            return None
        if not isinstance(entry.get("ai"), bool) or not isinstance(entry.get("killed", False), bool):
            return None
        return entry

    def enabled(self, feature: str, workspace: str) -> bool:
        entry = self._entry(feature)
        if entry is None:
            return False
        if entry.get("killed", False):
            return False
        if self.kills is not None and self.kills.killed(feature):
            return False
        if entry["ai"] and self.kills is None:
            return False  # an AI feature is never on without a kill switch that can turn it off
        return bucket(feature, workspace) < entry["rollout_percent"]

    def features(self) -> list[str]:
        doc = self.document if isinstance(self.document, dict) else {}
        return sorted(doc.get("features", {}) or {})
