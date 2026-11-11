"""Relay's admission check (4.29.0; ADR-046), standard library and cosign only.

    python tools/admit.py --policy deploy/admission/policy.json --version 4.29.0 --digests '{"relay": "sha256:..."}'
    python tools/admit.py --policy deploy/admission/policy.json --desired deploy/gitops/production.json

The first form is pipeline.yml's `admit` job (the digests release.yml pushed); the second is deploy.yml's check of
every image in production's desired state. Images are named `$REGISTRY/<image>@<digest>` (--registry, or the
REGISTRY environment variable). Exit 0 when every image is admitted, 1 when admission refuses (any finding).
There is no override.

The rules are relay-admission-v1's, as Lab 15.1's reference `admit()` applies them; here cosign does the
cryptography, against Sigstore's certificate authority and transparency log:

    AD001  an image is not referenced by a sha256 digest
    AD002  `cosign verify` fails: no signature, or one that does not verify (cosign also requires its
           transparency-log entry, AD004, unless told otherwise, and this tool never tells it otherwise)
    AD003  cosign reports that no certificate names the policy's exact identity and issuer for this version, or
           the version does not match the policy's `version_pattern`
    AD005  an attestation's signed subject is not the image's digest
    AD006  a required attestation is missing or does not verify under the exact identity and issuer
    AD007  an image the policy does not name
    AD008  no gate-results attestation, or one in which any gate did not succeed
    AD009  the release is on the policy's `revoked_releases` list

AD009 is checked once for the release; then image by image in sorted order. An image with AD001, AD007 or AD002
is not checked further. Every cosign call pins the exact identity (`--certificate-identity`, never a regexp) and
issuer. Build provenance is written by actions/attest-build-provenance as a Sigstore bundle stored as an OCI
referrer, so it is read with `--new-bundle-format` (cosign 2.4.0 or later); the other attestations are written by
`cosign attest`. That reading of cosign's documentation has not yet been checked against a real attestation
(Chapter 15's editor review, item 24).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PROVENANCE = "https://slsa.dev/provenance/v1"
COSIGN_TYPES = {"https://cyclonedx.org/bom": "cyclonedx", PROVENANCE: "slsaprovenance1"}
IDENTITY_MISMATCH = "expected identities"   # cosign: "none of the expected identities matched ..."

# run(command) -> (exit code, stdout, stderr). Tests pass a fake; nothing else in this file runs a process.
Runner = Callable[[list], "tuple[int, str, str]"]


@dataclass(frozen=True)
class Finding:
    rule: str
    image: str
    message: str


def run_process(cmd: list) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", f"{cmd[0]}: {exc}"
    return p.returncode, p.stdout, p.stderr


def _pins(identity: str, policy: dict) -> list[str]:
    return ["--certificate-identity", identity, "--certificate-oidc-issuer", policy["issuer"]]


def _statements(stdout: str) -> list[dict]:
    """The in-toto statements in cosign verify-attestation's output (one DSSE envelope per line)."""
    out = []
    for line in stdout.splitlines():
        try:
            env = json.loads(line)
            out.append(json.loads(base64.b64decode(env["payload"])))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def _subjects(statement: dict) -> set[str]:
    return {"sha256:" + str((s.get("digest") or {}).get("sha256")) for s in statement.get("subject") or []}


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "no output")


def _attestation(run: Runner, ref: str, digest: str, ptype: str, identity: str, policy: dict):
    """(rule, message) for a failure, or (None, the verified statements bound to `digest`)."""
    cmd = ["cosign", "verify-attestation"]
    if ptype == PROVENANCE:
        cmd.append("--new-bundle-format")
    cmd += ["--type", COSIGN_TYPES.get(ptype, ptype), *_pins(identity, policy), ref]
    code, stdout, stderr = run(cmd)
    if code != 0:
        rule = "AD003" if IDENTITY_MISMATCH in stderr else "AD006"
        return rule, f"{ptype}: {_first_line(stderr)}"
    statements = [s for s in _statements(stdout) if s.get("predicateType") == ptype]
    if not statements:
        return "AD006", f"{ptype}: cosign verified nothing of this type"
    bound = [s for s in statements if digest in _subjects(s)]
    if not bound:
        return "AD005", f"{ptype}: the signed subject is not {digest}"
    return None, bound


def admit(desired: dict, policy: dict, registry: str, run: Runner = run_process) -> list[Finding]:
    """Findings for one desired state ({"release": X.Y.Z, "images": {name: digest}}): AD009 first, then by image."""
    out: list[Finding] = []
    version = str(desired["release"])
    if version in policy.get("revoked_releases", []):
        out.append(Finding("AD009", "*", f"release {version} is revoked"))
    identity = policy["identity"].format(version=version)
    pattern = policy.get("version_pattern")
    gates = policy.get("gate_results")
    for name in sorted(desired.get("images", {})):
        digest = desired["images"][name]
        if name not in policy["images"]:
            out.append(Finding("AD007", name, "not an image this policy admits"))
            continue
        if not isinstance(digest, str) or not DIGEST.match(digest):
            out.append(Finding("AD001", name, f"referenced by {digest!r}, not a sha256 digest"))
            continue
        ref = f"{registry.rstrip('/')}/{name}@{digest}" if registry else f"{name}@{digest}"
        code, _, stderr = run(["cosign", "verify", *_pins(identity, policy), ref])
        if code != 0:
            rule = "AD003" if IDENTITY_MISMATCH in stderr else "AD002"
            out.append(Finding(rule, name, f"cosign verify: {_first_line(stderr)}"))
            continue
        if pattern and not re.fullmatch(pattern, version):
            out.append(Finding("AD003", name, f"version {version!r} is not a release version"))
        failed: dict[str, list[str]] = {}
        for ptype in policy["attestations"]:
            rule, result = _attestation(run, ref, digest, ptype, identity, policy)
            if rule:
                failed.setdefault(rule, []).append(result)
        for rule in sorted(failed):  # at most one finding per rule, as in Lab 15.1
            out.append(Finding(rule, name, "; ".join(failed[rule])))
        if gates:
            rule, result = _attestation(run, ref, digest, gates["type"], identity, policy)
            if rule:
                out.append(Finding("AD008", name, f"no gate-results attestation ({result})"))
            else:
                results = result[-1].get("predicate") or {}
                bad = sorted(g for g, want in gates["required"].items() if results.get(g) != want)
                if bad:
                    out.append(Finding("AD008", name, "gates that did not succeed: " + ", ".join(bad)))
    return out


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None, run: Runner = run_process) -> int:
    ap = argparse.ArgumentParser(prog="admit.py", description="Admission under relay-admission-v1 (ADR-046).")
    ap.add_argument("--policy", required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--desired", help="a desired-state file, such as deploy/gitops/production.json")
    group.add_argument("--digests", help='JSON from release.yml: {"image": "sha256:..."}')
    ap.add_argument("--version", help="the release's X.Y.Z version (with --digests)")
    ap.add_argument("--registry", default=os.environ.get("REGISTRY", ""))
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    policy = _load(args.policy)
    if args.desired:
        desired = _load(args.desired)
    else:
        if not args.version:
            ap.error("--digests needs --version")
        try:
            images = json.loads(args.digests)
        except ValueError:
            ap.error("--digests is not JSON")
        if not isinstance(images, dict) or not images:
            ap.error("--digests names no image")
        desired = {"release": args.version, "images": images}
    findings = admit(desired, policy, args.registry, run)
    for f in findings:
        sys.stdout.write(f"{f.rule} {f.image}: {f.message}\n")
    verdict = "refused" if findings else "admitted"
    sys.stdout.write(f"admission ({policy.get('policy')}): release {desired['release']} {verdict}, "
                     f"{len(findings)} finding(s)\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
