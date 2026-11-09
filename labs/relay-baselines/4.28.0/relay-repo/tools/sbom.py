"""Write the release's SBOM and AI-BOM as CycloneDX 1.6 JSON (4.25.0; ADR-030), standard library only.

    python tools/sbom.py --image-digest sha256:<64 hex> --date 2027-01-28 --out-dir dist

The SBOM lists what Relay's image is built from: Relay itself (standard library only), each
locked package in deploy/requirements.txt with its hash and source, and the base image by
digest. The AI-BOM lists what Relay's AI behaviour depends on: models, prompts, datasets,
evaluation gates, tool servers and the registered agents (supply-chain/ai-components.json and
governance/agents.json). Both are deterministic: the same inputs give the same bytes, so the
signature in the release workflow covers exactly what was reviewed.

What this tool does not do: list the packages inside the base image. A scan of the built image
(for example with Syft) does that, and the release attaches it alongside. CycloneDX has no
component type for a prompt or an agent, so prompts are `data` components and agents are
`services`, each with a `relay:kind` property.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from supplychain import HASH, REQ, logical_lines, normalize  # noqa: E402

SPEC = "1.6"


def _version(root: Path) -> str:
    return re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]


def _load(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _serial(kind: str, version: str, digest: str) -> str:
    return "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://relay.example/{kind}/{version}/{digest}"))


def _metadata(name: str, version: str, digest: str, date: str) -> dict:
    return {"timestamp": f"{date}T00:00:00Z",
            "tools": {"components": [{"type": "application", "name": "relay-tools-sbom", "version": version}]},
            "component": {"type": "container", "bom-ref": "relay-image", "name": name, "version": version,
                          "hashes": [{"alg": "SHA-256", "content": digest.removeprefix("sha256:")}]}}


def locked_packages(root: Path, rel: str = "deploy/requirements.txt") -> list[tuple[str, str, str]]:
    out = []
    for ln in logical_lines((root / rel).read_text(encoding="utf-8")):
        m = REQ.match(ln)
        if m:
            out.append((normalize(m[1]), m[2], HASH.findall(ln)[0]))
    return out


def build_sbom(root: Path, version: str, image_digest: str, date: str) -> dict:
    mirror = _load(root, "supply-chain/mirror.json")
    adr = {normalize(p["name"]): p["adr"] for p in mirror["projects"]}
    base = next(i for i in _load(root, "supply-chain/images.json")["images"] if i["file"] == "deploy/Containerfile")
    repo, tag = base["reference"].split(":")
    components = [{"type": "application", "bom-ref": f"pkg:generic/relay@{version}", "name": "relay",
                   "version": version, "purl": f"pkg:generic/relay@{version}",
                   "properties": [{"name": "relay:runtime-dependencies", "value": "none (standard library only)"}]},
                  {"type": "container", "bom-ref": "base-image", "name": repo, "version": tag,
                   "purl": f"pkg:oci/{repo}@{base['digest'].replace(':', '%3A')}"
                           f"?repository_url=docker.io/library/{repo}&tag={tag}",
                   "hashes": [{"alg": "SHA-256", "content": base["digest"].removeprefix("sha256:")}]}]
    for name, ver, digest in locked_packages(root):
        purl = f"pkg:pypi/{name}@{ver}"
        components.append({"type": "library", "bom-ref": purl, "name": name, "version": ver, "purl": purl,
                           "hashes": [{"alg": "SHA-256", "content": digest}],
                           "properties": [{"name": "relay:source", "value": mirror["index_url"]},
                                          {"name": "relay:adr", "value": adr.get(name, "none")}]})
    return {"bomFormat": "CycloneDX", "specVersion": SPEC, "serialNumber": _serial("sbom", version, image_digest),
            "version": 1, "metadata": _metadata("relay", version, image_digest, date), "components": components,
            "dependencies": [{"ref": "relay-image", "dependsOn": [c["bom-ref"] for c in components]}]}


def build_aibom(root: Path, version: str, image_digest: str, date: str) -> dict:
    ai = _load(root, "supply-chain/ai-components.json")
    agents = _load(root, "governance/agents.json")["agents"]
    allowed = set(ai["allowed_model_file_formats"])
    components, services = [], []
    for m in ai["models"]:
        if m["file_format"] is not None and m["file_format"] not in allowed:
            raise ValueError(f"model {m['name']}: file format {m['file_format']!r} is not allowed (ADR-030)")
        components.append({"type": "machine-learning-model", "bom-ref": f"model:{m['name']}", "name": m["name"],
                           "version": m["version"], "supplier": {"name": m["provider"]},
                           "modelCard": {"considerations": {"useCases": [m["used_by"]]}},
                           "properties": [{"name": "relay:kind", "value": "model"},
                                          {"name": "relay:reference", "value": m["reference"]},
                                          {"name": "relay:file-format", "value": m["file_format"] or "hosted"},
                                          {"name": "relay:owner", "value": m["owner"]}]})
    for p in ai["prompts"]:
        components.append({"type": "data", "bom-ref": f"prompt:{p['name']}", "name": p["name"],
                           "hashes": [{"alg": "SHA-256", "content": p["sha256"]}],
                           "data": [{"type": "configuration", "name": p["name"], "description": p["source"]}],
                           "properties": [{"name": "relay:kind", "value": "prompt"},
                                          {"name": "relay:used-by", "value": p["used_by"]},
                                          {"name": "relay:owner", "value": p["owner"]}]})
    for d in ai["datasets"]:
        components.append({"type": "data", "bom-ref": f"dataset:{d['name']}@{d['version']}", "name": d["name"],
                           "version": d["version"], "hashes": [{"alg": "SHA-256", "content": d["sha256"]}],
                           "data": [{"type": "dataset", "name": d["name"], "classification": d["classification"],
                                     "description": f"{d['records']} records; {d['use']}"}],
                           "properties": [{"name": "relay:kind", "value": "dataset"},
                                          {"name": "relay:owner", "value": d["owner"]}]})
    for e in ai["evaluations"]:
        components.append({"type": "data", "bom-ref": f"evaluation:{e['name']}", "name": e["name"],
                           "data": [{"type": "definition", "name": e["name"]}],
                           "properties": [{"name": "relay:kind", "value": "evaluation-gate"},
                                          {"name": "relay:status-check", "value": e["required_status_check"]},
                                          {"name": "relay:owner", "value": e["owner"]}]})
    for t in ai["tool_servers"]:
        services.append({"bom-ref": f"tool:{t['name']}", "name": t["name"], "version": t["version"],
                         "description": t["source"],
                         "properties": [{"name": "relay:kind", "value": "tool-server"},
                                        {"name": "relay:protocol", "value": t["protocol"]},
                                        {"name": "relay:launch", "value": " ".join([t["command"], *t["args"]])},
                                        {"name": "relay:sha256", "value": t["sha256"]},
                                        {"name": "relay:reviewed-by", "value": t["reviewed_by"]}]})
    for a in sorted(agents, key=lambda a: a["agent_id"]):
        services.append({"bom-ref": f"agent:{a['agent_id']}", "name": a["agent_id"], "authenticated": True,
                         "properties": [{"name": "relay:kind", "value": "agent"},
                                        {"name": "relay:owner", "value": a["owner"]},
                                        {"name": "relay:scopes", "value": ",".join(a["scopes"])}]})
    return {"bomFormat": "CycloneDX", "specVersion": SPEC, "serialNumber": _serial("aibom", version, image_digest),
            "version": 1, "metadata": _metadata("relay", version, image_digest, date), "components": components,
            "services": services}


def write(bom: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python tools/sbom.py", description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=None, help="release version (default: pyproject.toml)")
    ap.add_argument("--image-digest", required=True, help="sha256:<64 hex> of the built image")
    ap.add_argument("--date", required=True, help="release date, YYYY-MM-DD (the commit date in CI)")
    ap.add_argument("--out-dir", default="dist")
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args(argv)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_digest):
        ap.error("--image-digest must be sha256: followed by 64 hex digits")
    root = Path(args.root)
    version = args.version or _version(root)
    out = Path(args.out_dir)
    write(build_sbom(root, version, args.image_digest, args.date), out / "sbom.cdx.json")
    write(build_aibom(root, version, args.image_digest, args.date), out / "aibom.cdx.json")
    sys.stdout.write(f"wrote {out / 'sbom.cdx.json'} and {out / 'aibom.cdx.json'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
