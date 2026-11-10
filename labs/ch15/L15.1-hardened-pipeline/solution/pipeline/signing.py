"""A STAND-IN for Sigstore keyless signing and its transparency log (provided), as in Lab 13.1.

A bundle's "signature" is an HMAC-SHA256 over its certificate and statement with a published lab key, and its
transparency-log entry carries a second HMAC, with a second published key standing for the log's own signature
over the entry (`data/trust-root.json`). So a forged log entry fails as a forged signature does. The checks a
verifier makes are real; the cryptography is not. Real releases are verified with cosign against Sigstore's
certificate authority and transparency log (ADR-030, ADR-046).
"""

from __future__ import annotations

import hashlib
import hmac
import json


def payload(bundle: dict) -> bytes:
    return json.dumps({"certificate": bundle["certificate"], "statement": bundle["statement"]},
                      sort_keys=True).encode()


def sign(certificate: dict, statement: dict, key: str) -> dict:
    bundle = {"certificate": certificate, "statement": statement}
    bundle["signature"] = hmac.new(key.encode(), payload(bundle), hashlib.sha256).hexdigest()
    return bundle


def signature_ok(bundle: dict, key: str) -> bool:
    try:
        expected = hmac.new(key.encode(), payload(bundle), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(bundle.get("signature", "")))
    except (KeyError, TypeError):
        return False


def _entry(bundle: dict, tlog: dict) -> bytes:
    return json.dumps({"signature": bundle.get("signature"), "integrated_time": tlog.get("integrated_time"),
                       "log_index": tlog.get("log_index")}, sort_keys=True).encode()


def log(bundle: dict, integrated_time: str, log_index: int, log_key: str) -> dict:
    """Add a transparency-log entry the stand-in log has signed."""
    tlog = {"integrated_time": integrated_time, "log_index": log_index}
    tlog["log_signature"] = hmac.new(log_key.encode(), _entry(bundle, tlog), hashlib.sha256).hexdigest()
    return {**bundle, "tlog": tlog}


def log_entry_ok(bundle: dict, log_key: str) -> bool:
    tlog = bundle.get("tlog") or {}
    expected = hmac.new(log_key.encode(), _entry(bundle, tlog), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(tlog.get("log_signature", "")))
