"""LAB-ADV-2027-0113, as a test of the safe behaviour: a token whose expiry is not a number must be refused."""

import sys

import sessionkeel
import signin

NOW = 1_810_000_000
token = sessionkeel.sign({"sub": "u1", "iat": NOW - 90000, "exp": str(NOW - 86400)}, signin.KEY)
accepted = signin.check(token, NOW) is not None
print("expired token accepted" if accepted else "expired token refused")
sys.exit(1 if accepted else 0)
