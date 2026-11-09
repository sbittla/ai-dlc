"""Relay's supply-chain check (4.25.0; ADR-028), standard library only.

    python tools/supplychain.py              # check the repository; exit 1 on any finding
    python tools/supplychain.py --json       # the findings as JSON

It reads the committed files only; it never contacts a registry. Rules:

    SC001  a requirement in a lock file is not pinned with == and a sha256 hash
    SC002  a lock file names an index other than the mirror, or adds one (--extra-index-url, -f, --trusted-host)
    SC003  a lock file does not refuse source distributions (--only-binary :all:) or hash-checking (--require-hashes)
    SC004  a locked project, version or hash is not the one admitted in supply-chain/mirror.json
    SC005  pyproject.toml declares a runtime dependency (ADR-007's AR5 keeps it empty)
    SC006  an image is referenced by tag, not by digest, or its digest differs from supply-chain/images.json
    SC007  a GitHub Actions step uses an action that is not pinned to a full commit SHA
    SC008  an MCP server in .mcp.json is not the one recorded in supply-chain/ai-components.json (same launch
           command and arguments, and a record with a reviewed sha256 and reviewer). It does NOT hash the server's
           code: relaymcp is resolved from the import path at launch, so a launch-time hash check is still needed.
    SC009  a pip install outside the lock files, or without --require-hashes
    SC010  pip's defaults in the dev container or the agent sandbox are not: mirror index, wheels only, hashes
           required (PIP_INDEX_URL, PIP_ONLY_BINARY=:all:, PIP_REQUIRE_HASHES=1). github.com stays reachable for
           git, so without these an ad hoc `pip install git+https://...` would fetch and build source.

The run is the `supply-chain` required status check and a pre-commit hook.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_FILES = ("deploy/requirements.txt", "requirements-dev.txt")
REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})\b")
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    message: str


def normalize(name: str) -> str:
    """PEP 503 name normalization: runs of -, _ and . are equal, and case does not matter."""
    return re.sub(r"[-_.]+", "-", name).lower()


def logical_lines(text: str) -> list[str]:
    """Join backslash continuations and drop comments and blank lines."""
    out, buf = [], ""
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            out.append(" ".join(buf.split()))
        buf = ""
    return out


def check_lock(path: str, text: str, mirror: dict) -> list[Finding]:
    admitted = {normalize(p["name"]): {f["version"]: f["sha256"] for f in p["files"]} for p in mirror["projects"]}
    lines = logical_lines(text)
    out: list[Finding] = []
    options = [ln for ln in lines if ln.startswith("-")]
    index = [ln.split(None, 1)[1] if " " in ln else ln.split("=", 1)[-1] for ln in options
             if ln.startswith(("--index-url", "-i "))]
    if index != [mirror["index_url"]]:
        out.append(Finding("SC002", path, f"index must be exactly the mirror {mirror['index_url']}, found {index}"))
    for ln in options:
        if ln.startswith(("--extra-index-url", "-f", "--find-links", "--trusted-host", "--no-index")):
            out.append(Finding("SC002", path, f"option not allowed in a lock file: {ln.split()[0]}"))
    if "--only-binary :all:" not in options and "--only-binary=:all:" not in options:
        out.append(Finding("SC003", path, "lock file must refuse source distributions: --only-binary :all:"))
    if "--require-hashes" not in options:
        out.append(Finding("SC003", path, "lock file must turn on hash-checking: --require-hashes"))
    for ln in lines:
        if ln.startswith("-"):
            continue
        m = REQ.match(ln)
        hashes = HASH.findall(ln)
        if not m or not hashes:
            out.append(Finding("SC001", path, f"not pinned with == and a sha256 hash: {ln.split()[0]}"))
            continue
        name, version = normalize(m[1]), m[2]
        if name not in admitted:
            out.append(Finding("SC004", path, f"{m[1]} is not admitted to the mirror (supply-chain/mirror.json)"))
        elif version not in admitted[name]:
            out.append(Finding("SC004", path, f"{m[1]}=={version} is not an admitted version"))
        elif admitted[name][version] not in hashes:
            out.append(Finding("SC004", path, f"{m[1]}=={version}: hash differs from the admitted file"))
    return out


def image_references(root: Path) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    dc = root / ".devcontainer" / "devcontainer.json"
    if dc.exists():
        refs.append((".devcontainer/devcontainer.json", json.loads(dc.read_text(encoding="utf-8"))["image"]))
    for cf in sorted((root / "deploy").rglob("Containerfile")):
        for ln in cf.read_text(encoding="utf-8").splitlines():
            if ln.startswith("FROM "):
                refs.append((cf.relative_to(root).as_posix(), ln.split()[1]))
    return refs


def check_images(root: Path, images: dict) -> list[Finding]:
    pinned = {(i["file"], i["reference"]): i["digest"] for i in images["images"]}
    out: list[Finding] = []
    for path, ref in image_references(root):
        if not DIGEST.search(ref):
            out.append(Finding("SC006", path, f"image '{ref}' is referenced by tag, not by digest"))
            continue
        name, digest = ref.split("@", 1)
        if pinned.get((path, name)) != digest:
            out.append(Finding("SC006", path, f"image '{name}' digest is not the reviewed one in supply-chain/images.json"))
    compute = root / "infra" / "compute.tf"
    if compute.exists():
        text = compute.read_text(encoding="utf-8")
        for m in re.finditer(r'^\s*(image|proxy_image)\s*=\s*"([^"]+)"', text, re.M):
            if "@${var." not in m[2] or ":${var." in m[2]:
                out.append(Finding("SC006", "infra/compute.tf", f"{m[1]} must be referenced by digest: {m[2]}"))
    return out


def check_workflows(root: Path) -> list[Finding]:
    out: list[Finding] = []
    for wf in sorted((root / ".github" / "workflows").glob("*.yml")):
        rel = wf.relative_to(root).as_posix()
        for n, ln in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)", ln)
            if m and not m[1].startswith(("./", "docker://")) and not SHA_PIN.match(m[1]):
                out.append(Finding("SC007", rel, f"line {n}: action '{m[1]}' is not pinned to a full commit SHA"))
            if m and m[1].startswith("docker://") and not DIGEST.search(m[1]):
                out.append(Finding("SC007", rel, f"line {n}: container action '{m[1]}' is not pinned by digest"))
    return out


def check_pip_installs(root: Path) -> list[Finding]:
    out: list[Finding] = []
    files = [p for p in (root / ".github" / "workflows").glob("*.yml")]
    files += list((root / "deploy").rglob("Containerfile")) + [root / ".devcontainer" / "devcontainer.json"]
    for f in sorted(p for p in files if p.exists()):
        rel = f.relative_to(root).as_posix()
        for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "pip install" in ln and not ln.lstrip().startswith("#"):
                if "--require-hashes" not in ln or " -r " not in ln:
                    out.append(Finding("SC009", rel, f"line {n}: pip install must use a lock file with --require-hashes"))
    return out


def check_mcp(root: Path, ai: dict) -> list[Finding]:
    path = root / ".mcp.json"
    if not path.exists():
        return []
    recorded = {s["name"]: s for s in ai["tool_servers"]}
    out: list[Finding] = []
    for name, server in json.loads(path.read_text(encoding="utf-8"))["mcpServers"].items():
        rec = recorded.get(name)
        if rec is None:
            out.append(Finding("SC008", ".mcp.json", f"MCP server '{name}' is not recorded in ai-components.json"))
        elif (server.get("command"), server.get("args")) != (rec["command"], rec["args"]):
            out.append(Finding("SC008", ".mcp.json", f"MCP server '{name}' launch differs from the reviewed one"))
        elif not re.fullmatch(r"[0-9a-f]{64}", rec.get("sha256", "")) or not rec.get("reviewed_by"):
            out.append(Finding("SC008", ".mcp.json", f"MCP server '{name}' has no pinned source hash or reviewer"))
    return out


PIP_DEFAULTS = {"PIP_ONLY_BINARY": ":all:", "PIP_REQUIRE_HASHES": "1"}


def check_pip_defaults(root: Path, mirror: dict) -> list[Finding]:
    want = dict(PIP_DEFAULTS, PIP_INDEX_URL=mirror["index_url"])
    out: list[Finding] = []
    dc = root / ".devcontainer" / "devcontainer.json"
    if dc.exists():
        env = json.loads(dc.read_text(encoding="utf-8")).get("containerEnv", {})
        for k, v in want.items():
            if env.get(k) != v:
                out.append(Finding("SC010", ".devcontainer/devcontainer.json", f"containerEnv {k} must be {v!r}"))
    compute = root / "infra" / "compute.tf"
    if compute.exists():
        text = compute.read_text(encoding="utf-8")
        start = text.find('resource "aws_ecs_task_definition" "sandbox"')
        end = text.find('resource "', start + 1)
        block = text[start:end if end > 0 else len(text)] if start >= 0 else ""
        for k, v in want.items():
            if f'{{ name = "{k}", value = "{v}" }}' not in block:
                out.append(Finding("SC010", "infra/compute.tf", f"sandbox task must set {k}={v}"))
    return out


def check(root: Path = ROOT) -> list[Finding]:
    sc = root / "supply-chain"
    mirror = json.loads((sc / "mirror.json").read_text(encoding="utf-8"))
    images = json.loads((sc / "images.json").read_text(encoding="utf-8"))
    ai = json.loads((sc / "ai-components.json").read_text(encoding="utf-8"))
    out: list[Finding] = []
    for rel in LOCK_FILES:
        p = root / rel
        if p.exists():
            out += check_lock(rel, p.read_text(encoding="utf-8"), mirror)
        else:
            out.append(Finding("SC001", rel, "lock file missing"))
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    if not re.search(r"^dependencies = \[\]", pyproject, re.M):
        out.append(Finding("SC005", "pyproject.toml", "runtime dependencies must stay empty (AR5) without an ADR"))
    out += check_images(root, images) + check_workflows(root) + check_pip_installs(root) + check_mcp(root, ai)
    out += check_pip_defaults(root, mirror)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    findings = check(Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT)
    if "--json" in argv:
        sys.stdout.write(json.dumps([asdict(f) for f in findings], indent=2) + "\n")
    else:
        for f in findings:
            sys.stdout.write(f"{f.rule} {f.path}: {f.message}\n")
        sys.stdout.write(f"supply-chain: {len(findings)} finding(s)\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
