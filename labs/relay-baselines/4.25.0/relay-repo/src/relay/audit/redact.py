"""Redaction of secrets and personal data before anything is logged (added in 4.23.0; ADR-023).

Every string that leaves an agent's request path for a log, a trace or the audit trail passes
through `redact` first. It replaces credentials and direct identifiers with typed markers and
counts what it replaced, so a report can say "3 emails, 1 token" without showing either.

Redaction is a pattern match, not a guarantee. It finds the formats listed in PATTERNS; a name
written in a ticket's free text, or a secret in a format nobody listed, passes through. Known misses,
pinned by tests/test_audit_redact.py: a token encoded (for example in base64) outside an authorization
header, and phone numbers written in national format without a country code. That is
why ADR-023 also keeps prompt and response bodies out of the audit trail entirely and gives traces
a 30-day retention: minimization first, redaction as the second layer.
"""

from __future__ import annotations

import re
from collections import Counter

# Order matters: credentials first, so a token inside an email-like string is caught as a token.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("relay-token", re.compile(r"\brly_(?:live|test)_[0-9a-f]{32}\b")),
    ("agent-token", re.compile(r"\brla_[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("auth-header", re.compile(r"(?i)\b(authorization:\s*[A-Za-z][\w-]*|bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"(?<![\w+])\+\d{1,3}[ -]?\d(?:[ -]?\d){6,12}\b")),
)

# Mapping keys whose values are always replaced whole, whatever they contain.
SENSITIVE_KEYS = frozenset({"authorization", "password", "secret", "token", "api_key", "cookie", "set-cookie"})


def marker(kind: str) -> str:
    return f"[redacted:{kind}]"


def redact(text: str) -> tuple[str, Counter]:
    """Return `text` with every match of PATTERNS replaced by its marker, and the counts by kind."""
    counts: Counter = Counter()
    for kind, pattern in PATTERNS:
        def swap(m: re.Match[str], kind: str = kind) -> str:
            counts[kind] += 1
            if kind == "auth-header":
                return f"{m.group(1)} {marker(kind)}"
            return marker(kind)
        text = pattern.sub(swap, text)
    return text, counts


def redact_value(value, counts: Counter | None = None):
    """Redact a JSON-like value recursively: strings by pattern, sensitive keys whole.

    Returns the redacted copy; the input is not modified. Pass `counts` to accumulate the totals.
    """
    counts = Counter() if counts is None else counts
    if isinstance(value, str):
        clean, found = redact(value)
        counts.update(found)
        return clean
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS and item is not None:
                counts["sensitive-key"] += 1
                out[key] = marker("sensitive-key")
            else:
                out[key] = redact_value(item, counts)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_value(item, counts) for item in value]
    return value
