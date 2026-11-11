"""Relay's web sign-in, reduced to what Lab 19.1 needs (a stand-in; the real service is outside the snapshot)."""

import sessionkeel

KEY = b"lab-19-1-constant-not-a-secret"
SESSION_SECONDS = 12 * 3600


def issue(user, now):
    """The session token sign-in hands out. It has never carried an audience."""
    return sessionkeel.sign({"sub": user, "iat": now, "exp": now + SESSION_SECONDS}, KEY)


def check(token, now):
    """The user a session token names, or None."""
    try:
        return sessionkeel.verify(token, KEY, now)["sub"]
    except sessionkeel.InvalidToken:
        return None
