"""The web application's tests as they stood in May 2027 (run as a plain script in the sandbox)."""

import sys

import sessionkeel
import signin

NOW = 1_810_000_000
failures = []
good = sessionkeel.sign({"sub": "u1", "iat": NOW, "exp": NOW + 60, "aud": "relay-web"}, signin.KEY)
if sessionkeel.verify(good, signin.KEY, NOW, audience="relay-web")["sub"] != "u1":
    failures.append("valid token")
for name, token, kw in [
        ("tampered", good[:-2] + "AA", {"audience": "relay-web"}),
        ("expired", sessionkeel.sign({"sub": "u1", "iat": NOW, "exp": NOW - 600, "aud": "relay-web"}, signin.KEY),
         {"audience": "relay-web"}),
        ("wrong audience", good, {"audience": "relay-admin"})]:
    try:
        sessionkeel.verify(token, signin.KEY, NOW, **kw)
        failures.append(name + " accepted")
    except sessionkeel.InvalidToken:
        pass
print("; ".join(failures) if failures else "4 app tests passed")
sys.exit(1 if failures else 0)
