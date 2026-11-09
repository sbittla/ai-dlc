"""Build the canonical Relay 4.28.0 from the three Batch 6 branches.

All three started from canonical 4.25.0:

- Chapter 12 (Relay 4.26.0): defences for untrusted text (render.py, marked
  ticket text, run taint, memory trust, the email adapter, content-checked
  egress), ADR-032 to ADR-035.
- Chapter 16 (its own 4.27.0): telemetry, SLOs, alerting and deployed
  detection (relay/telemetry/, service middleware, monitor, infra/monitoring/),
  ADR-036 to ADR-039.
- Chapter 17 (its own 4.28.0): load tests, performance budgets, the leasing
  limiter and cost controls (relay/routing/, tools/loadtest.py, perf/),
  ADR-040 to ADR-043.

Apart from AGENTS.md, CODEOWNERS and the version strings, the branches changed
disjoint files. This script takes Chapter 12's tree as the base, copies the
files only Chapter 16 or Chapter 17 changed, and three-way merges the shared
files with `git merge-file` against 4.25.0 after normalising the version
strings and the AGENTS.md overview. Lines that two branches added at the same
place are all kept, in chapter order. Run:

    python labs/relay-baselines/merge_4_28_0.py

Output: labs/relay-baselines/4.28.0/relay-repo/ (later chapters copy from here).
"""

from __future__ import annotations

import filecmp
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LABS = Path(__file__).resolve().parent.parent
BASE = LABS / "relay-baselines/4.25.0/relay-repo"
CH12 = LABS / "ch12/L12.1-agentic-red-team/relay-repo"
CH16 = LABS / "ch16/L16.1-otel-redaction-slo/relay-repo"
CH17 = LABS / "ch17/L17.1-load-test-bottleneck/relay-repo"
OUT = LABS / "relay-baselines/4.28.0/relay-repo"
SKIP_PARTS = {"__pycache__", ".pytest_cache", "evidence"}
SKIP_SUFFIXES = (".db", ".db-wal", ".db-shm", ".egg-info")
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.db", "*.db-*", "*.egg-info", "evidence")

SHARED = [
    "AGENTS.md",
    ".github/CODEOWNERS",
    "pyproject.toml",
    "src/relay/__init__.py",
    "tests/test_service_app.py",
    "tests/test_service_http.py",
    "tests/test_service_wsgi.py",
]
VERSIONS = ("4.25.0", "4.26.0", "4.27.0", "4.28.0")
OVERVIEW = re.compile(r"security gates, signed SBOMs and the deployment wiring \(4\.25\.0\).*?\n(?=Python 3\.11\+)", re.S)
FINAL_OVERVIEW = (
    "security gates, signed SBOMs and the deployment wiring (4.25.0), defences for untrusted text: marked\n"
    "ticket text, constrained summaries, safe rendering, the email adapter and content-checked egress (4.26.0),\n"
    "telemetry, SLOs, alerting and deployed detection (4.27.0), and load tests, performance budgets and cost\n"
    "controls for model calls (4.28.0).\n"
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
    """Make the lines every branch changed in the same way identical before merging."""
    if name == "AGENTS.md":
        if len(OVERVIEW.findall(text)) != 1:
            raise SystemExit("AGENTS.md overview not found exactly once")
        return OVERVIEW.sub(FINAL_OVERVIEW, text)
    if name in ("pyproject.toml", "src/relay/__init__.py") or name.startswith("tests/test_service_"):
        for v in VERSIONS:
            text = text.replace(f'"{v}"', '"4.28.0"')
    return text


def merge_shared(name: str) -> None:
    base_text, _ = read(BASE / name)
    current, nl = read(CH12 / name)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "base").write_text(normalise(name, base_text), encoding="utf-8", newline="\n")
        (t / "current").write_text(normalise(name, current), encoding="utf-8", newline="\n")
        for branch in (CH16, CH17):
            (t / "other").write_text(normalise(name, read(branch / name)[0]), encoding="utf-8", newline="\n")
            subprocess.run(["git", "merge-file", "--union", str(t / "current"), str(t / "base"), str(t / "other")],
                           check=True)
        merged = (t / "current").read_text(encoding="utf-8")
    if "<<<<<<<" in merged or ">>>>>>>" in merged:
        raise SystemExit(f"unresolved conflict in {name}")
    (OUT / name).write_bytes(merged.replace("\n", nl).encode("utf-8"))


def main() -> None:
    for tree in (BASE, CH12, CH16, CH17):
        if not tree.is_dir():
            raise SystemExit(f"missing tree: {tree}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(CH12, OUT, ignore=IGNORE)

    base_files = files(BASE)
    claimed: dict[str, str] = {}
    for label, branch in (("Chapter 12", CH12), ("Chapter 16", CH16), ("Chapter 17", CH17)):
        for name in sorted(files(branch)):
            if name in SHARED:
                continue
            if name in base_files and filecmp.cmp(BASE / name, branch / name, shallow=False):
                continue
            if name in claimed:
                raise SystemExit(f"{name} changed by both {claimed[name]} and {label}; merge it by hand")
            claimed[name] = label
            if branch is not CH12:
                (OUT / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(branch / name, OUT / name)
        for name in sorted(base_files - files(branch)):
            raise SystemExit(f"{label} deleted {name}; merge it by hand")

    for name in SHARED:
        merge_shared(name)

    # Integration edit: Chapter 16's telemetry test pins the service version it was written at.
    name = "tests/test_telemetry_signals.py"
    text, nl = read(OUT / name)
    old = '"service.version": "4.27.0"'
    if text.count(old) != 1:
        raise SystemExit(f"expected one pinned version in {name}")
    (OUT / name).write_bytes(text.replace(old, '"service.version": "4.28.0"').replace("\n", nl).encode("utf-8"))

    print(f"wrote canonical Relay 4.28.0 to {OUT} ({len(claimed)} branch-owned files)")


if __name__ == "__main__":
    main()
