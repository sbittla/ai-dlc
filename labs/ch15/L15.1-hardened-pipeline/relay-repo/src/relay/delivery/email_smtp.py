"""The email delivery adapter (added in 4.26.0; ADR-033). The one module outside the service that may send.

It reads email items from the escalation engine's outbox and sends each one at most once. Escalations,
hourly summaries and rule notices are all accepted: spec 1.2.0 says an adapter must accept every kind the
contract lists, and `rule_notice` has no other consumer.

The checks, in order, for each item not yet finished:

1. unknown_kind     the item's kind is not one of ACCEPTED_KINDS
2. mismatch         the stored message does not parse, or names a different kind or user than the item
3. no_address       the user has no address in Relay's directory. The address never comes from the message
4. foreign_link     the subject or body holds an address outside `link_base`. The engine writes only Relay
                    links, so anything else means the outbox row was not written by the engine
5. suppressed       relay.notify says not to send (ESC-R10): a spam mark suppresses email to that user
6. sent / failed    the transport sends it; an error is retried on the next pass, up to `max_attempts`

Escalation emails are pages and rule notices are security notices, so a muted type never silences them:
for both the adapter asks `relay.notify` as for a security notice, which only a spam mark suppresses (the
characterized rule 1 in ADR-018; ESC-R10). The hourly summary of held escalations is a digest, so a user's
mute of `digest` (or of "all") suppresses it, as it would any digest. Every outcome,
refusals included, is written to `email_delivery`, which is the adapter's audit record. Showing a
suppressed escalation on the task and the rule's page (ESC-AC16) needs the service; this module records
what the service will read.
"""

from __future__ import annotations

import json
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage as MimeMessage
from typing import Callable, Mapping, Protocol

from ..escalation import EscalationStore
from ..notify import Prefs, decide

ACCEPTED_KINDS = ("escalation", "summary", "rule_notice")
NOTIFY_TYPE = {"escalation": "security", "rule_notice": "security", "summary": "digest"}  # for relay.notify
FINAL = ("sent", "suppressed", "refused", "failed")
# Any scheme (any case), a scheme-relative address, or a www. host. The engine writes only Relay links.
_ADDRESS_IN_TEXT = re.compile(r"[a-z][a-z0-9+.-]*://[^\s<>\"')]+|(?<![\w:/])//[^\s<>\"')]+|\bwww\.[^\s<>\"')]+",
                              re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS email_delivery (
    outbox_id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    to_user TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('retry', 'sent', 'suppressed', 'refused', 'failed')),
    reason TEXT,
    attempts INTEGER NOT NULL,
    at TEXT NOT NULL
);
"""


class Transport(Protocol):
    def send(self, sender: str, to: str, subject: str, body: str) -> None: ...


@dataclass
class SmtpTransport:
    """Sends through the email provider's SMTP endpoint with STARTTLS. Never used by the tests."""

    host: str
    port: int = 587
    timeout_s: float = 10.0

    def send(self, sender: str, to: str, subject: str, body: str) -> None:
        message = MimeMessage()
        message["From"], message["To"], message["Subject"] = sender, to, subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.send_message(message)


@dataclass
class RecordingTransport:
    """Keeps what would have been sent: for tests, local runs and the lab's red team."""

    sent: list = field(default_factory=list)
    fail_times: int = 0  # fail this many sends first, to exercise retries

    def send(self, sender: str, to: str, subject: str, body: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise OSError("simulated provider error")
        self.sent.append({"from": sender, "to": to, "subject": subject, "body": body})


@dataclass(frozen=True)
class Delivery:
    outbox_id: int
    kind: str
    to_user: str
    status: str          # retry | sent | suppressed | refused | failed
    reason: str | None   # the refusal or suppression code, or the error's type


class EmailAdapter:
    def __init__(self, store: EscalationStore, addresses: Mapping[int, str], prefs: Callable[[int], Prefs],
                 transport: Transport, sender: str, link_base: str, max_attempts: int = 3) -> None:
        if not link_base.startswith("https://"):
            raise ValueError("link_base must be an https address")
        self.store, self.addresses, self.prefs = store, addresses, prefs
        self.transport, self.sender = transport, sender
        self.link_base = link_base.rstrip("/") + "/"
        self.max_attempts = max_attempts
        self.conn = store.conn
        self.conn.executescript(SCHEMA)

    def _row(self, outbox_id: int):
        return self.conn.execute("SELECT status, attempts FROM email_delivery WHERE outbox_id = ?",
                                 (outbox_id,)).fetchone()

    def _record(self, item, to_user: str, status: str, reason: str | None, attempts: int, now: datetime) -> Delivery:
        self.conn.execute(
            "INSERT INTO email_delivery (outbox_id, kind, to_user, status, reason, attempts, at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (outbox_id) DO UPDATE SET status = excluded.status,"
            " reason = excluded.reason, attempts = excluded.attempts, at = excluded.at",
            (item.id, item.kind, to_user, status, reason, attempts,
             now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        return Delivery(item.id, item.kind, to_user, status, reason)

    def _problem(self, item) -> tuple[str | None, dict | None]:
        if item.kind not in ACCEPTED_KINDS:
            return "unknown_kind", None
        try:
            doc = json.loads(item.body)
        except (json.JSONDecodeError, TypeError):
            return "mismatch", None
        if (not isinstance(doc, dict) or doc.get("kind") != item.kind or str(doc.get("to_user")) != item.recipient
                or not isinstance(doc.get("subject"), str) or not isinstance(doc.get("body"), str)):
            return "mismatch", None
        if doc["to_user"] not in self.addresses:
            return "no_address", doc
        text = doc["subject"] + "\n" + doc["body"]
        if any(not url.startswith(self.link_base) for url in _ADDRESS_IN_TEXT.findall(text)):  # case-sensitive
            return "foreign_link", doc
        return None, doc

    def deliver(self, now: datetime) -> list[Delivery]:
        """One pass over the outbox's email items. Returns what happened to each item it looked at."""
        out = []
        for item in self.store.outbox():
            if item.channel != "email":
                continue
            row = self._row(item.id)
            if row is not None and row[0] != "retry":
                continue
            attempts = 0 if row is None else row[1]
            problem, doc = self._problem(item)
            if problem is not None:
                out.append(self._record(item, item.recipient, "refused", problem, attempts, now))
                continue
            decision = decide(self.prefs(doc["to_user"]), NOTIFY_TYPE[item.kind], now)
            if not decision.send:
                out.append(self._record(item, item.recipient, "suppressed", decision.reason, attempts, now))
                continue
            try:
                self.transport.send(self.sender, self.addresses[doc["to_user"]], doc["subject"], doc["body"])
            except Exception as exc:  # noqa: BLE001 - a provider error is an outcome, retried, never a crash
                attempts += 1
                status = "failed" if attempts >= self.max_attempts else "retry"
                out.append(self._record(item, item.recipient, status, type(exc).__name__, attempts, now))
                continue
            out.append(self._record(item, item.recipient, "sent", None, attempts + 1, now))
        return out

    def log(self) -> list[dict]:
        rows = self.conn.execute("SELECT outbox_id, kind, to_user, status, reason, attempts FROM email_delivery"
                                 " ORDER BY outbox_id").fetchall()
        keys = ("outbox_id", "kind", "to_user", "status", "reason", "attempts")
        return [dict(zip(keys, r)) for r in rows]
