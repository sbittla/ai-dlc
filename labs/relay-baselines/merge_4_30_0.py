"""Build the canonical Relay 4.30.0 from the two Batch 7 branches.

Both started from canonical 4.28.0:

- Chapter 15 (Relay 4.29.0): the delivery pipeline: admission of signed images,
  canary releases, kill switches for AI features and a test sandbox with no
  network, ADR-044 to ADR-048.
- Chapter 18 (its own 4.30.0): agents in production: durable agent jobs, the
  effect ledger, the sandbox for agent-written code and the agent gateway,
  ADR-049 to ADR-052.

Apart from AGENTS.md, CODEOWNERS and the version strings, the branches changed
disjoint files. This script takes Chapter 15's tree as the base, copies the
files only Chapter 18 changed, and three-way merges the shared files with
`git merge-file --union` against 4.28.0 after normalising the version strings
and the AGENTS.md overview. Run:

    python labs/relay-baselines/merge_4_30_0.py

Output: labs/relay-baselines/4.30.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import filecmp
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
BASE = LABS / "relay-baselines/4.28.0/relay-repo"
CH15 = LABS / "ch15/L15.1-hardened-pipeline/relay-repo"
CH18 = LABS / "ch18/L18.1-durable-sandboxed-workers/relay-repo"
OUT = LABS / "relay-baselines/4.30.0/relay-repo"
SKIP_PARTS = {"__pycache__", ".pytest_cache", "evidence", ".venv", "venv"}
SKIP_SUFFIXES = (".db", ".db-wal", ".db-shm", ".egg-info")
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*", "*.egg-info", "evidence",
                                ".venv", "venv")

SHARED = [
    "AGENTS.md",
    ".github/CODEOWNERS",
    "pyproject.toml",
    "src/relay/__init__.py",
    "tests/test_service_app.py",
    "tests/test_service_http.py",
    "tests/test_service_wsgi.py",
    "tests/test_telemetry_signals.py",
]
VERSIONED = {"pyproject.toml", "src/relay/__init__.py", "tests/test_service_app.py", "tests/test_service_http.py",
             "tests/test_service_wsgi.py", "tests/test_telemetry_signals.py"}
VERSIONS = ("4.28.0", "4.29.0", "4.30.0")
OVERVIEW = re.compile(r"controls for model calls \(4\.28\.0\).*?\n(?=Python 3\.11\+)", re.S)
FINAL_OVERVIEW = (
    "controls for model calls (4.28.0), the delivery pipeline: admission of signed images, canary releases,\n"
    "kill switches for AI features and a test sandbox with no network (4.29.0), and agents in production:\n"
    "durable agent jobs, the effect ledger, the sandbox for agent-written code and the agent gateway (4.30.0).\n"
)


def files(root: Path) -> set[str]:
    out = set()
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not SKIP_PARTS & set(rel.parts) and not any(
                part.endswith(SKIP_SUFFIXES) for part in rel.parts):
            out.add(rel.as_posix())
    return out


def read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def normalise(name: str, text: str) -> str:
    """Make the lines both branches changed in the same way identical before merging."""
    if name == "AGENTS.md":
        if len(OVERVIEW.findall(text)) != 1:
            raise SystemExit("AGENTS.md overview not found exactly once")
        return OVERVIEW.sub(FINAL_OVERVIEW, text)
    if name in VERSIONED:
        for v in VERSIONS:
            text = text.replace(f'"{v}"', '"4.30.0"')
    return text


def merge_shared(name: str) -> None:
    base_text, _ = read(BASE / name)
    current, nl = read(CH15 / name)
    other, _ = read(CH18 / name)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "base").write_text(normalise(name, base_text), encoding="utf-8", newline="\n")
        (t / "current").write_text(normalise(name, current), encoding="utf-8", newline="\n")
        (t / "other").write_text(normalise(name, other), encoding="utf-8", newline="\n")
        subprocess.run(["git", "merge-file", "--union", str(t / "current"), str(t / "base"), str(t / "other")],
                       check=True)
        merged = (t / "current").read_text(encoding="utf-8")
    if "<<<<<<<" in merged or ">>>>>>>" in merged:
        raise SystemExit(f"unresolved conflict in {name}")
    (OUT / name).write_bytes(merged.replace("\n", nl).encode("utf-8"))


def main() -> None:
    for tree in (BASE, CH15, CH18):
        if not tree.is_dir():
            raise SystemExit(f"missing tree: {tree}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH15, OUT, ignore=IGNORE)

    base_files = files(BASE)
    claimed: dict[str, str] = {}
    for label, branch in (("Chapter 15", CH15), ("Chapter 18", CH18)):
        for name in sorted(files(branch)):
            if name in SHARED:
                continue
            if name in base_files and filecmp.cmp(BASE / name, branch / name, shallow=False):
                continue
            if name in claimed:
                raise SystemExit(f"{name} changed by both {claimed[name]} and {label}; merge it by hand")
            claimed[name] = label
            if branch is not CH15:
                (OUT / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(branch / name, OUT / name)
        for name in sorted(base_files - files(branch)):
            raise SystemExit(f"{label} deleted {name}; merge it by hand")

    for name in SHARED:
        merge_shared(name)

    # Integration edit: Chapter 15's production desired state names the release it deploys, and a test checks
    # it equals pyproject's version. The canonical tree is 4.30.0; the image digests stay labelled stand-ins.
    name = "deploy/gitops/production.json"
    text, nl = read(OUT / name)
    old = '"release": "4.29.0"'
    if text.count(old) != 1:
        raise SystemExit(f"expected one release field in {name}")
    (OUT / name).write_bytes(text.replace(old, '"release": "4.30.0"').replace("\n", nl).encode("utf-8"))

    print(f"wrote canonical Relay 4.30.0 to {OUT} ({len(claimed)} branch-owned files)")


if __name__ == "__main__":
    main()
