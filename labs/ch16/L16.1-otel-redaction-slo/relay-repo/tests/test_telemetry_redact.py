"""Telemetry redaction (4.27.0, ADR-036): keys allowlisted, values redacted, known bypasses closed, known misses
pinned. Every probe is written by hand; the fake token and the addresses are not real."""

import base64

import pytest

from relay.audit.redact import redact as audit_redact
from relay.telemetry.redact import clean_attributes, decode_variants, leaks, redact_text

TOKEN = "rly_live_" + "0123456789abcdef" * 2
EMAIL = "jane.doe@example.com"

CLOSED_BYPASSES = [  # each passes 4.23.0's relay.audit.redact unchanged, and 4.27.0 catches it
    ("double percent-encoded email", "jane.doe%2540example.com", "encoded-email"),
    ("percent-encoded dots", "jane%2Edoe%40example%2Ecom", "encoded-email"),
    ("HTML entity", "jane&#64;example.com", "email"),
    ("JSON escape", "jane\\u0040example.com", "email"),
    ("full-width at sign", "jane＠example.com", "email"),
    ("zero-width space", "jane​@example.com", "email"),
    ("base64 email", base64.b64encode(EMAIL.encode()).decode(), "encoded-email"),
    ("base64url token outside a header", base64.urlsafe_b64encode(f"harvester:{TOKEN}".encode()).decode(),
     "encoded-relay-token"),
    ("hex email", EMAIL.encode().hex(), "encoded-email"),
    ("cookie header", "Cookie: session=abc123; theme=dark", "cookie"),
    ("API-key header", "X-Api-Key: 9f8e7d6c5b4a", "api-key-header"),
    ("token in a query string", "GET /v1/x?token=abc123&page=2", "query-secret"),
    ("German national phone", "call 030 1234567", "phone"),
    ("UK national phone", "call 020 7946 0958", "phone"),
    ("French national phone", "call 06 12 34 56 78", "phone"),
    ("North American phone", "call (415) 555-0134", "phone"),
    ("IPv4 address", "from 203.0.113.45", "ip"),
    ("JSON Web Token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop", "jwt"),
    # Round 1 review: encoded values after a key, IPv6, secret-named fields, short base64.
    ("base64 email after a key", "user=" + base64.b64encode(EMAIL.encode()).decode(), "encoded-email"),
    ("base64 email after a colon", "user:" + base64.b64encode(EMAIL.encode()).decode(), "encoded-email"),
    ("base64 email in a path", "/v1/u/" + base64.b64encode(EMAIL.encode()).decode(), "encoded-email"),
    ("base64 bearer after a key", "tok=" + base64.b64encode(b"Bearer abcdefghijklmnop").decode(),
     "encoded-auth-header"),
    ("hex email after a key", "h=" + EMAIL.encode().hex(), "encoded-email"),
    ("short base64 email", base64.b64encode(b"ab@cd.io").decode(), "encoded-email"),
    ("IPv6 address", "from 2001:db8:85a3::8a2e:370:7334 today", "ip"),
    ("JSON authorization", '{"authorization":"abcdefghijklmnopqrstu"}', "secret-field"),
    ("JSON password", '{"password":"hunter2hunter2"}', "secret-field"),
    ("key=value password", "password=hunter2hunter2", "secret-field"),
    ("colon password", "password: hunter2", "secret-field"),
    ("refresh token", "refresh_token=abcdef123456", "secret-field"),
]


@pytest.mark.parametrize("name,text,kind", CLOSED_BYPASSES, ids=[c[0] for c in CLOSED_BYPASSES])
def test_bypasses_of_the_audit_redactor_are_closed(name, text, kind):
    assert sum(audit_redact(text)[1].values()) == 0  # 4.23.0 misses it
    clean, counts = redact_text(text)
    assert counts[kind] >= 1 and f"[redacted:{kind}]" in clean


@pytest.mark.parametrize("text", [f"Authorization: Bearer {TOKEN}", f"contact {EMAIL}", "call +44 20 7946 0958"])
def test_what_the_audit_redactor_caught_is_still_caught(text):
    assert sum(audit_redact(text)[1].values()) >= 1
    assert sum(redact_text(text)[1].values()) >= 1


KNOWN_MISSES = [
    "jane dot doe at example dot com",       # spelled out
    "call 4155550134",                        # one run of digits, no prefix or separators
    base64.b64encode(b"alice:hunter2").decode(),  # a plain password: no format to match
    "Jane Doe, 12 Harbour Street",            # names and addresses in free text
]


@pytest.mark.parametrize("text", KNOWN_MISSES)
def test_known_misses_are_pinned(text):
    assert sum(redact_text(text)[1].values()) == 0


def test_deeper_encoding_is_beyond_the_decoder_and_says_so():
    once = "jane.doe%2540example.com"  # %25 40 -> %40 -> @: two layers
    triple = once.replace("%25", "%252525")  # four layers before the at sign appears
    assert redact_text(once)[1] and not redact_text(triple)[1]


@pytest.mark.parametrize("text", ["version 4.27.0 on 2027-02-02 at 15:04:00", "network 203.0.113.0/24",
                                  "network 2001:db8:1234::/48", "at 15:04:00 ratio 3:4:5", "mac aa:bb:cc:dd:ee:ff",
                                  "trace 4bf92f3577b34da6a3ce929d0e0e4736", "job 02 02 2027", "price 0.25 1234 5678",
                                  "sha 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"])
def test_ordinary_values_are_left_alone(text):
    assert redact_text(text) == (text, {})


def test_keys_are_allowlisted_and_content_keys_always_dropped():
    clean, counts = clean_attributes({"http.route": "/v1/x", "http.request.header.authorization": "Bearer x",
                                      "gen_ai.input.messages": "hello", "user.email": EMAIL,
                                      "relay.agent.stop_reason": f"budget:usd for {EMAIL}"})
    assert clean == {"http.route": "/v1/x", "relay.agent.stop_reason": "budget:usd for [redacted:email]"}
    assert counts == {"unknown-key": 2, "content-key": 1, "email": 1}


def test_decoding_stops_after_two_layers():
    assert decode_variants("%2540") == ["%40", "@"]
    assert leaks("nothing here") == {}
