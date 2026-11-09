"""Redaction for telemetry: spans, metrics and logs (added in 4.27.0; ADR-036).

Telemetry is minimised first and redacted second, as ADR-023 decided for the audit trail.

1. **Keys.** Only attribute keys in `semconv.ALLOWED` leave the process. Content attributes (prompts,
   responses, tool arguments) are dropped whatever their value, and so is any key nobody reviewed, such as
   `http.request.header.authorization`. Dropped keys are counted, never shown.
2. **Values.** Every string value passes through `relay.audit.redact` (4.23.0) and then through this
   module's additions, which close the bypasses Chapter 14's review found and Lab 16.1's probe set pins:
   values hidden by percent-encoding (also double), HTML entities, `\\u` escapes, base64 or base64url,
   full-width or zero-width characters, hex, also after a key (`user=`, `tok:`, a path); national phone formats;
   JSON Web Tokens; cookies, API-key headers, secrets in query strings and secret-named fields in JSON or
   key=value form; IPv4 and IPv6 addresses (personal data in the EU).

A segment that decodes to something sensitive is replaced whole, as `[redacted:encoded-<kind>]`.

Known misses, pinned by `tests/test_telemetry_redact.py`: names and addresses in free text, an email
address spelled out ("jane dot doe at example dot com"), a secret in a format nobody listed (for example a
plain password, base64-encoded or not), a phone number written as one run of digits with no prefix, and
values encoded in more layers than the decoder reads (two, beyond the single `%40` that 4.23.0 reads).
Redaction is a second layer; the first is not putting content in telemetry at all.
"""

from __future__ import annotations

import base64
import binascii
import html
import ipaddress
import re
import unicodedata
from collections import Counter

from ..audit.redact import redact as _audit_redact
from . import semconv

_IPV4 = r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\w.]|/\d)"
_IPV6 = r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:.]|/\d)"
EXTRA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("cookie", re.compile(r"(?i)\b(?:set-)?cookie\s*[:=]\s*[^\r\n]+")),
    ("api-key-header", re.compile(r"(?i)\b(?:x-api-key|api-key|x-auth-token|proxy-authorization)\s*[:=]\s*\S+")),
    ("query-secret", re.compile(r"(?i)(?<=[?&;])(?:access_token|id_token|token|api_key|apikey|key|password|passwd"
                                r"|pwd|secret|session|sig|signature|code|email)=[^&#\s]+")),
    # Key names containing passport, password, pwd, secret, token or credential (user_password, x_auth_token,
    # credentials), or exactly pass, auth, authorization, an API key, cookie or session; "author" and "passage"
    # do not match, and keys ending in _count, _limit and the like are numbers (_COUNT_KEY).
    ("secret-field", re.compile(r"(?i)([\"']?)\b((?:[\w-]*(?:passwd|password|passport|pwd|secret|token"
                                r"|credential)[\w-]*)"
                                r"|pass|auth|authorization|[\w-]*api[_-]?key|cookie|session(?:_?id)?)\1"
                                r"(\s*[:=]\s*)(?![\"']?\[redacted|[\"']?(?:bearer|basic)\b)"
                                r"(\"[^\"]*\"|'[^']*'|[^\s,;&}\"']+)")),
    ("ip", re.compile(_IPV4)),
    ("ip", re.compile(_IPV6)),
    # National formats: a trunk prefix 0 or a bracketed area code, then groups; and the North American form.
    ("phone", re.compile(r"(?<![\w+])(?:\(0?\d{2,5}\)[ .-]?|0\d{1,4}[ ./-])\d{2,8}(?:[ .-]\d{2,4}){0,4}(?!\w)")),
    ("phone", re.compile(r"(?<![\w+])\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)")),
)
_COUNT_KEY = re.compile(r"(?i)[_-](?:count|counts|length|limit|limits|total|usage|type)$")
_SEGMENT = re.compile(r"[^\s\"'<>(),;\[\]{}|]{8,}")
_SEPARATORS = re.compile(r"[=:/.#~_-]+")
_B64 = re.compile(r"^[A-Za-z0-9+/_-]{8,}={0,2}$")
_HEX = re.compile(r"^(?:[0-9a-f]{2}){8,}$|^(?:[0-9A-F]{2}){8,}$")
_PCT = re.compile(r"%([0-9A-Fa-f]{2})")
_UESC = re.compile(r"\\u([0-9A-Fa-f]{4})")
MAX_DEPTH = 2  # decode at most twice: covers double encoding, and says so


def marker(kind: str) -> str:
    return f"[redacted:{kind}]"


def normalise(text: str) -> str:
    """HTML entities and \\u escapes decoded, NFKC (full-width forms become ASCII), and no format characters
    (zero-width spaces and joiners). Exported text is the normalised form."""
    if "&" in text:
        text = html.unescape(text)
    if "\\u" in text:
        text = _UESC.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _phone_digits_ok(match: str) -> bool:
    digits = sum(ch.isdigit() for ch in match)
    return 9 <= digits <= 12


def _is_ipv6(text: str) -> bool:
    try:
        return ipaddress.ip_address(text).version == 6
    except ValueError:
        return False


def _plain(text: str, counts: Counter) -> str:
    text, found = _audit_redact(text)
    counts.update(found)
    for kind, pattern in EXTRA_PATTERNS:
        def swap(m: re.Match[str], kind: str = kind) -> str:
            if kind == "phone" and not _phone_digits_ok(m.group(0)):
                return m.group(0)
            if kind == "ip" and ":" in m.group(0) and not _is_ipv6(m.group(0)):
                return m.group(0)
            if kind == "secret-field" and _COUNT_KEY.search(m.group(2)):
                return m.group(0)  # token_count=1234 is a number about tokens, not a token
            counts[kind] += 1
            if kind == "query-secret":
                return m.group(0).split("=", 1)[0] + "=" + marker(kind)
            if kind == "secret-field":
                return m.group(1) + m.group(2) + m.group(1) + m.group(3) + marker(kind)
            return marker(kind)
        text = pattern.sub(swap, text)
    return text


def _pct_decode(text: str) -> str:
    raw = _PCT.sub(lambda m: chr(int(m.group(1), 16)), text.replace("+", " "))
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _b64_decode(text: str) -> str | None:
    """Base64, base64url or hex, if `text` is entirely one of them and decodes to readable text."""
    try:
        if _HEX.match(text):  # hashes and IDs are hex too: they decode to bytes that are not text
            decoded = bytes.fromhex(text).decode("utf-8")
        elif _B64.match(text):
            body = text.rstrip("=").replace("-", "+").replace("_", "/")
            decoded = base64.b64decode(body + "=" * (-len(body) % 4), validate=True).decode("utf-8")
        else:
            return None
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    printable = sum(ch.isprintable() for ch in decoded)
    return decoded if decoded and printable >= 0.9 * len(decoded) else None


def decode_variants(segment: str, depth: int = MAX_DEPTH) -> list[str]:
    """Every decoding of `segment` up to `depth` layers: percent, HTML entities, \\u escapes, base64."""
    out, frontier = [], [segment]
    for _ in range(depth):
        nxt = []
        for value in frontier:
            for decoded in (_pct_decode(value) if "%" in value else None,
                            html.unescape(value) if "&" in value else None,
                            _UESC.sub(lambda m: chr(int(m.group(1), 16)), value) if "\\u" in value else None,
                            _b64_decode(value)):
                if decoded and decoded != value and decoded not in out:
                    out.append(normalise(decoded))
                    nxt.append(decoded)
        frontier = nxt
    return out


def _sensitive_kind(text: str) -> str | None:
    counts: Counter = Counter()
    _plain(text, counts)
    return min(counts) if counts else None


def redact_text(text: str, counts: Counter | None = None) -> tuple[str, Counter]:
    """Return `text` with credentials and personal data replaced by markers, and the counts by kind."""
    counts = Counter() if counts is None else counts
    text = _plain(normalise(text), counts)

    def swap(m: re.Match[str]) -> str:
        segment = m.group(0)
        if segment.startswith("[redacted:"):
            return segment
        # The whole segment, and each part between separators (`=:/.#~_-`), so `user=<base64>` is decoded too.
        parts = [segment] + [p for p in _SEPARATORS.split(segment) if len(p) >= 8 and p != segment]
        for part in parts:
            for variant in decode_variants(part):
                kind = _sensitive_kind(variant)
                if kind is not None:
                    counts["encoded-" + kind] += 1
                    return marker("encoded-" + kind)
        return segment
    return _SEGMENT.sub(swap, text), counts


def clean_value(value, counts: Counter):
    if isinstance(value, str):
        return redact_text(value, counts)[0]
    if isinstance(value, (list, tuple)):
        return [clean_value(v, counts) for v in value]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    counts["non-scalar"] += 1  # dicts and objects are not attribute values; drop their content
    return marker("non-scalar")


def clean_attributes(attributes: dict, counts: Counter | None = None) -> tuple[dict, Counter]:
    """Keep allowlisted keys only, drop content keys, and redact every remaining string value."""
    counts = Counter() if counts is None else counts
    out = {}
    for key, value in attributes.items():
        if key in semconv.CONTENT_KEYS:
            counts["content-key"] += 1
        elif key not in semconv.ALLOWED:
            counts["unknown-key"] += 1
        elif value is not None:
            out[key] = clean_value(value, counts)
    return out, counts


def leaks(text: str) -> Counter:
    """What `redact_text` would still replace in already-exported text: the leak scan for runtime checks."""
    _, counts = redact_text(text)
    return counts
