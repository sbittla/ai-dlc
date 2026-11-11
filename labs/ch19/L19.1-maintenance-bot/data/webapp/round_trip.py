"""Added after the 20 May incident: the token sign-in issues must be accepted by the check sign-in runs."""

import sys

import signin

NOW = 1_810_000_000
ok = signin.check(signin.issue("u1", NOW), NOW) == "u1"
print("round trip ok" if ok else "a token sign-in issued was refused")
sys.exit(0 if ok else 1)
