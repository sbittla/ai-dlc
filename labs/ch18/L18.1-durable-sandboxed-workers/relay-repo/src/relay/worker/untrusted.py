"""Untrusted ticket text on its way into and out of the model (added in 4.26.0; ADR-032).

A ticket is written by whoever filed it. Chapter 2 called such text untrusted input, and Chapter 12's
incident showed what it can carry. This module does three things with it, none of which makes injection
impossible; they make it rarer and its effects smaller.

`mark` wraps ticket text before the model sees it ("spotlighting"). Hidden characters are removed, the
text is put between an opening and a closing line that carry a per-ticket nonce (an HMAC under the
worker's secret, so a ticket's author cannot predict it), and any line in the text that imitates either
marker is neutralized, so a ticket cannot close its own envelope. The prompt tells the model that text
between the markers is data. This lowers obedience; it does not remove it.

`unmark` recovers the text from an envelope (for the simulated model and for tests).

`parse_summary` is the constraint on what the model may write back for people to read. It is an
ALLOWLIST, not a filter for known patterns: a summary may hold only letters, digits, spaces and a short
list of punctuation, at most 400 characters, and no token shaped like a host name or an email address.
There is no slash, bracket, angle bracket, at sign, backslash or hash, so no address, link reference,
Markdown or HTML can be written at all, whatever its encoding. Anything else is refused and the reason
recorded: Relay drops the summary rather than repairing it, as it does for the suggestion (Chapter 2).

`parse_summary` deliberately shares no code with `relay.render`, so that one bug cannot defeat both.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from ..render import strip_hidden

SUMMARY_MAX = 400
_OPEN = "<<untrusted ticket nonce={nonce}>>"
_CLOSE = "<<end of ticket nonce={nonce}>>"
_ENVELOPE = re.compile(r"\A<<untrusted ticket nonce=([0-9a-f]{12})>>\n(.*)\n<<end of ticket nonce=\1>>\Z", re.S)
_MARKER_LIKE = re.compile(r"<<\s*(?:untrusted|end of ticket)[^>]*>>", re.I)

# The only characters a summary may hold besides letters and digits (str.isalnum) and the plain space.
SUMMARY_PUNCTUATION = frozenset(".,;:'!?()-%&+\"‘’“”")
# A dotted token whose last label is two or more letters (any script) or an IDN label looks like a host name.
_HOSTLIKE = re.compile(r"[^\W_](?:[\w-]*[^\W_])?(?:\.[^\W_](?:[\w-]*[^\W_])?)*\.(?:[^\W\d_]{2,}|xn--[\w-]+)(?![\w-])")


def nonce_for(source_id: str, text: str, secret: bytes) -> str:
    """12 hex characters of an HMAC under the worker's secret: a ticket's author cannot predict it."""
    return hmac.new(secret, f"{source_id}\x00{text}".encode("utf-8"), hashlib.sha256).hexdigest()[:12]


def mark(text: str, source_id: str, secret: bytes) -> str:
    """The ticket text in a spotlighting envelope (see the module docstring)."""
    clean, _ = strip_hidden(text)
    clean = _MARKER_LIKE.sub("[marker removed]", clean)
    nonce = nonce_for(source_id, clean, secret)
    return "\n".join([_OPEN.format(nonce=nonce), clean, _CLOSE.format(nonce=nonce)])


def unmark(text: str) -> tuple[str, bool]:
    """(the text inside an envelope, True), or (the text unchanged, False) if it is not an envelope."""
    match = _ENVELOPE.match(text)
    return (match.group(2), True) if match else (text, False)


def parse_summary(text: str) -> tuple[str | None, str | None]:
    """(summary, None) if `text` is an acceptable summary, else (None, reason).

    Reasons, checked in this order: not_text, empty, too_long, characters (anything outside the allowlist,
    hidden characters included), address (a host-like or email-like token).
    """
    if not isinstance(text, str):
        return None, "not_text"
    stripped = text.strip()
    if not stripped:
        return None, "empty"
    if len(stripped) > SUMMARY_MAX:
        return None, "too_long"
    if any(not (ch.isalnum() or ch == " " or ch in SUMMARY_PUNCTUATION) for ch in stripped):
        return None, "characters"
    if _HOSTLIKE.search(stripped):
        return None, "address"
    return stripped, None
