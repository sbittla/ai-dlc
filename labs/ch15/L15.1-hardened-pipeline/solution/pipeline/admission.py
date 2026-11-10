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
    out: list[Finding] = []
    version = desired["release"]
    if version in policy.get("revoked_releases", []):
        out.append(Finding("AD009", "*", f"release {version} is revoked"))
    identity = policy["identity"].format(version=version)
    pattern = policy.get("version_pattern")
    gates = policy.get("gate_results")
    for name in sorted(desired.get("images", {})):
        ref = desired["images"][name]
        if name not in policy["images"]:
            out.append(Finding("AD007", name, "not an image this policy admits"))
            continue
        if not isinstance(ref, str) or not DIGEST.match(ref):
            out.append(Finding("AD001", name, f"referenced by {ref!r}, not a sha256 digest"))
            continue
        bundle = bundles.get(name)
        if not bundle or not signature_ok(bundle, trust["hmac_key"]):
            out.append(Finding("AD002", name, "no bundle" if not bundle else "signature does not verify"))
            continue
        cert, statement = bundle["certificate"], bundle["statement"]
        if cert.get("issuer") != policy["issuer"] or cert.get("identity") != identity:
            out.append(Finding("AD003", name, f"signed by {cert.get('identity')}, not {identity}"))
        elif pattern and not re.fullmatch(pattern, version):
            out.append(Finding("AD003", name, f"version {version!r} is not a release version"))
        tlog = bundle.get("tlog")
        if policy.get("require_tlog", True):
            if not tlog:
                out.append(Finding("AD004", name, "no transparency-log entry"))
            elif not log_entry_ok(bundle, trust["log_key"]):
                out.append(Finding("AD004", name, "log entry not signed by the log"))
            elif not _ts(cert["not_before"]) <= _ts(tlog["integrated_time"]) <= _ts(cert["not_after"]):
                out.append(Finding("AD004", name, "log entry outside the certificate's validity"))
        if statement.get("subject") != ref:
            out.append(Finding("AD005", name, "the signature is for a different digest"))
        bound = [a for a in statement.get("attestations", []) if a.get("subject") == ref]
        have = {a.get("type") for a in bound}
        missing = [t for t in policy["attestations"] if t not in have]
        if missing:
            out.append(Finding("AD006", name, "attestations missing or bound elsewhere: " + ", ".join(missing)))
        if gates:
            results = next((a.get("predicate") for a in bound if a.get("type") == gates["type"]), None)
            if results is None:
                out.append(Finding("AD008", name, "no gate-results attestation"))
            else:
                bad = sorted(g for g, want in gates["required"].items() if results.get(g) != want)
                if bad:
                    out.append(Finding("AD008", name, "gates that did not succeed: " + ", ".join(bad)))
    return out
