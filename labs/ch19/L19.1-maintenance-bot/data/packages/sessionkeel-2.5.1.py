"""sessionkeel 2.5.1: a FICTIONAL session-token library written for Relay's Lab 19.1. Not a real package; inert."""

import base64
import hashlib
import hmac
import json

__version__ = "2.5.1"


class InvalidToken(Exception):
    pass


def _b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(claims, key):
    body = _b64(json.dumps(claims, sort_keys=True).encode("utf-8"))
    return body + "." + _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())


def verify(token, key, now, audience=None, require_audience=True, leeway=60):
    body, _, mac = token.partition(".")
    good = _b64(hmac.new(key, body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, good):
        raise InvalidToken("signature")
    claims = json.loads(_unb64(body))
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or isinstance(exp, bool):
        raise InvalidToken("exp must be a number")
    if now > exp + leeway:
        raise InvalidToken("expired")
    if claims.get("iat", 0) > now + leeway:
        raise InvalidToken("issued in the future")
    aud = claims.get("aud")
    if aud is not None and audience is not None and aud != audience:
        raise InvalidToken("audience")
    if require_audience and (aud is None or aud != audience):
        raise InvalidToken("audience required")
    return claims
