"""Release evidence: a signed bundle, an SBOM and an AI-BOM, checked before deployment (TODO 5 in starter/).

The bundles in data/releases/ are SIMULATED. Their "signature" is an HMAC with a published stand-in key
(trust-root.json), so it shows the checks a verifier makes, not cryptographic strength. Real releases are
verified with cosign against Sigstore's certificate authority and transparency log (ADR-030).

    REL001  the signature does not verify over the certificate and statement
    REL002  the certificate's issuer or identity is not the release workflow at this version's tag
    REL003  no transparency-log entry, or it was integrated outside the certificate's validity
    REL004  the statement's subject digest is not the artifact's digest
    REL005  the SBOM or AI-BOM file differs from the digest the statement signed
    REL006  the SBOM lacks a locked package (purl and hash) or the base image digest
    REL007  the AI-BOM lacks a model, prompt, dataset, evaluation gate, tool server or registered agent
    REL008  the AI-BOM lists a model file in a format that can run code when loaded
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from datetime import datetime
from pathlib import Path

from . import RELAY, load_json


def relay_tools():
    """Relay 4.25.0's own tools/ (provided): the lock-file reader and the AI component list."""
    if str(RELAY / "tools") not in sys.path:
        sys.path.insert(0, str(RELAY / "tools"))
    import sbom
    return sbom


def signature_ok(bundle: dict, trust: dict) -> bool:
    """Recompute the stand-in signature (provided)."""
    payload = json.dumps({"certificate": bundle["certificate"], "statement": bundle["statement"]},
                         sort_keys=True).encode()
    expected = hmac.new(trust["hmac_key"].encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, bundle["signature"])


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def expected_inventory(relay_root: Path = RELAY) -> dict:
    """What a complete release lists, from Relay's own records (provided)."""
    sbom = relay_tools()
    ai = load_json(relay_root / "supply-chain" / "ai-components.json")
    agents = load_json(relay_root / "governance" / "agents.json")["agents"]
    base = next(i for i in load_json(relay_root / "supply-chain" / "images.json")["images"]
                if i["file"] == "deploy/Containerfile")
    return {"packages": {(f"pkg:pypi/{n}@{v}", h) for n, v, h in sbom.locked_packages(relay_root)},
            "base_digest": base["digest"].removeprefix("sha256:"),
            "ai_refs": ({f"model:{m['name']}" for m in ai["models"]} | {f"prompt:{p['name']}" for p in ai["prompts"]}
                        | {f"dataset:{d['name']}@{d['version']}" for d in ai["datasets"]}
                        | {f"evaluation:{e['name']}" for e in ai["evaluations"]}
                        | {f"tool:{t['name']}" for t in ai["tool_servers"]}
                        | {f"agent:{a['agent_id']}" for a in agents}),
            "allowed_formats": set(ai["allowed_model_file_formats"]) | {"hosted"}}


def check_release(bundle_dir: Path, trust: dict, version: str, relay_root: Path = RELAY) -> list[tuple[str, str]]:
    """Return (rule, message) pairs for one release candidate, in rule order (REL001 ... REL008).

    Files in bundle_dir: bundle.json, artifact.json, sbom.cdx.json, aibom.cdx.json. Compare file digests as
    sha256 of the files' bytes. The expected identity is trust["expected_identity"] with {version} filled.
    For REL006, every (purl, sha256) in expected_inventory()["packages"] must appear among the SBOM's
    components, and a component with bom-ref "base-image" must carry the base digest. For REL007, every
    expected bom-ref must appear among the AI-BOM's components and services (one message listing the
    missing refs, sorted). For REL008, any component whose "relay:file-format" property is not allowed.
    Give at most one message per rule.
    """
    b = load_json(bundle_dir / "bundle.json")
    art = load_json(bundle_dir / "artifact.json")
    sbom_bytes, ai_bytes = (bundle_dir / "sbom.cdx.json").read_bytes(), (bundle_dir / "aibom.cdx.json").read_bytes()
    out = []
    if not signature_ok(b, trust):
        out.append(("REL001", "signature does not verify"))
    cert = b["certificate"]
    identity = trust["expected_identity"].format(version=version)
    if cert["issuer"] != trust["expected_issuer"] or cert["identity"] != identity:
        out.append(("REL002", f"signed by {cert['identity']}, not {identity}"))
    tlog = b.get("tlog")
    if not tlog:
        out.append(("REL003", "no transparency-log entry"))
    elif not _ts(cert["not_before"]) <= _ts(tlog["integrated_time"]) <= _ts(cert["not_after"]):
        out.append(("REL003", "log entry outside the certificate's validity"))
    subject = b["statement"]["subject"][0]["digest"]["sha256"]
    if "sha256:" + subject != art["digest"]:
        out.append(("REL004", "statement subject is not the artifact's digest"))
    pred = b["statement"]["predicate"]
    if (hashlib.sha256(sbom_bytes).hexdigest() != pred["sbom_sha256"]
            or hashlib.sha256(ai_bytes).hexdigest() != pred["aibom_sha256"]):
        out.append(("REL005", "a BOM differs from what was signed"))
    exp = expected_inventory(relay_root)
    sb, ai = json.loads(sbom_bytes), json.loads(ai_bytes)
    have = {(c.get("purl"), h["content"]) for c in sb["components"] for h in c.get("hashes", [])}
    base_ok = any(c.get("bom-ref") == "base-image" and c["hashes"][0]["content"] == exp["base_digest"]
                  for c in sb["components"])
    missing_pkgs = sorted(p for p, h in exp["packages"] if (p, h) not in have)
    if missing_pkgs or not base_ok:
        out.append(("REL006", "SBOM incomplete: " + ", ".join(missing_pkgs + ([] if base_ok else ["base image"]))))
    refs = {c["bom-ref"] for c in ai.get("components", []) + ai.get("services", [])}
    missing = sorted(exp["ai_refs"] - refs)
    if missing:
        out.append(("REL007", "AI-BOM incomplete: " + ", ".join(missing)))
    bad = sorted(c["name"] for c in ai.get("components", [])
                 for p in c.get("properties", []) if p["name"] == "relay:file-format"
                 and p["value"] not in exp["allowed_formats"])
    if bad:
        out.append(("REL008", "model file format not allowed: " + ", ".join(bad)))
    return out
