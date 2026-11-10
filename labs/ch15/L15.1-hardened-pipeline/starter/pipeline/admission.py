"""Admission: which images the production reconciler may run (TODO 4 in starter/).

Policy: Relay's `deploy/admission/policy.json` (relay-admission-v1). Bundles are signed with the stand-in in
`signing.py`; the trust root is `data/trust-root.json` (`hmac_key` for signatures, `log_key` for log entries).

    AD001  an image in the desired state is not referenced by a sha256 digest (a tag, or nothing)
    AD002  an image has no bundle, or its signature does not verify
    AD003  the certificate's issuer or identity is not exactly the policy's for this release's version, or the
           version does not match the policy's `version_pattern` (X.Y.Z: a `vtrain-…` tag is not a release)
    AD004  no transparency-log entry, an entry the log did not sign, or one outside the certificate's validity
    AD005  the signed statement's subject is not the digest in the desired state
    AD006  a required attestation is missing, or is bound to a different digest
    AD007  an image the policy does not name
    AD008  no gate-results attestation bound to the digest, or one in which any gate did not succeed
    AD009  the release is on the policy's `revoked_releases` list

AD009 is checked once for the release, before any image. Then, image by image in sorted order, at most one
finding per rule. An image with AD001 or AD007 is not checked further; nor is one with AD002.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .signing import log_entry_ok, signature_ok

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class Finding:
    rule: str
    image: str
    message: str


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def admit(desired: dict, bundles: dict, policy: dict, trust: dict) -> list[Finding]:
    """Findings for one desired state: the release-level AD009 first, then image by image (sorted)."""
    raise NotImplementedError("TODO 4: admit")
