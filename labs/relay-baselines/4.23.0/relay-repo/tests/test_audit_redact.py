"""Redaction before logging (4.23.0, ADR-023). Secret-shaped test values are built from pieces so that the
workspace's own secret scan (Lab 3.1, WS010) does not mistake this file for a leak."""

from collections import Counter

from relay.audit import redact, redact_value

RELAY_TOKEN = "rly_" + "live_" + "0123456789abcdef" * 2
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" + "k1L2m3N4o5P6q7R8"


def test_each_credential_format_is_replaced_by_its_marker():
    text = f"t={RELAY_TOKEN} k={AWS_KEY} g={GITHUB_TOKEN}"
    clean, counts = redact(text)
    assert clean == "t=[redacted:relay-token] k=[redacted:aws-key] g=[redacted:github-token]"
    assert counts == Counter({"relay-token": 1, "aws-key": 1, "github-token": 1})


def test_an_encoded_token_in_an_authorization_header_is_still_caught():
    # The incident's token appeared base64-encoded, which secret masking keyed on the raw value missed.
    clean, counts = redact("> Authorization: Basic cmx5X2xpdmVfMGYxZTJkM2M0YjVhNjk3ODg3OTZhNWI0YzNkMmUxZjA6")
    assert clean == "> Authorization: Basic [redacted:auth-header]"
    assert counts == Counter({"auth-header": 1})


def test_emails_and_phone_numbers_are_replaced():
    clean, counts = redact('{"requester": "mara.ilves@example.com", "phone": "+44 20 7946 0001"}')
    assert clean == '{"requester": "[redacted:email]", "phone": "[redacted:phone]"}'
    assert counts == Counter({"email": 1, "phone": 1})


def test_ordinary_text_and_numbers_pass_unchanged():
    text = "Cannot log in after SSO change; 3 retries; ticket 48210; version 4.23.0"
    assert redact(text) == (text, Counter())


def test_sensitive_keys_are_replaced_whole_and_nested_values_redacted():
    counts = Counter()
    value = {"Authorization": "anything at all", "rows": 3,
             "nested": [{"note": "mail j.okafor@example.net"}, {"password": None}]}
    clean = redact_value(value, counts)
    assert clean == {"Authorization": "[redacted:sensitive-key]", "rows": 3,
                     "nested": [{"note": "mail [redacted:email]"}, {"password": None}]}
    assert counts == Counter({"sensitive-key": 1, "email": 1})


def test_redact_value_does_not_modify_its_input():
    value = {"note": "mail lin.wei@example.org"}
    redact_value(value)
    assert value == {"note": "mail lin.wei@example.org"}


def test_other_authorization_schemes_and_url_encoded_emails_are_caught():
    clean, counts = redact("Authorization: Token abcdefgh12345678 and ana%40example.com")
    assert clean == "Authorization: Token [redacted:auth-header] and [redacted:email]"
    assert counts == Counter({"auth-header": 1, "email": 1})


def test_known_misses_are_pinned():
    # A token encoded outside a header, and a national-format phone number, pass through. Minimization,
    # not redaction, is the control for both (ADR-023).
    encoded = "cmx5X2xpdmVfMGYxZTJkM2M0YjVhNjk3ODg3OTZhNWI0YzNkMmUxZjA6"
    for text in (f"payload={encoded}", "call me on 020 7946 0958"):
        assert redact(text) == (text, Counter())
