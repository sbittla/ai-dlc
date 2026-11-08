"""Findings, the check catalogue, policy loading and file helpers (provided; no TODOs here)."""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

SEVERITIES = ("critical", "high", "medium", "low")
AREAS = ("instructions", "secrets", "sandbox", "branch", "mcp")

# check id -> (severity, area, short title). Severity is fixed per check, so two
# people auditing the same repository always get the same counts.
CHECKS: dict[str, tuple[str, str, str]] = {
    "WS001": ("high", "instructions", "agent instructions file missing"),
    "WS002": ("medium", "instructions", "required section missing from instructions"),
    "WS003": ("low", "instructions", "instructions file longer than the policy allows"),
    "WS004": ("medium", "instructions", "required command missing from the Commands section"),
    "WS010": ("critical", "secrets", "secret-like string in a file"),
    "WS011": ("high", "secrets", "forbidden file committed"),
    "WS020": ("high", "sandbox", "sandbox (dev container) configuration missing"),
    "WS021": ("critical", "sandbox", "host path mounted into the sandbox"),
    "WS022": ("high", "sandbox", "container run argument not on the allowlist"),
    "WS023": ("low", "sandbox", "base image not pinned by digest"),
    "WS030": ("high", "branch", "branch protection export missing"),
    "WS031": ("high", "branch", "too few required approving reviews"),
    "WS032": ("medium", "branch", "code-owner review not required"),
    "WS033": ("high", "branch", "required status check missing"),
    "WS034": ("high", "branch", "administrators can bypass protection"),
    "WS035": ("high", "branch", "force pushes allowed"),
    "WS036": ("medium", "branch", "CODEOWNERS file missing"),
    "WS037": ("medium", "branch", "an approval survives later pushes"),
    "WS040": ("high", "mcp", "MCP server not on the allowlist"),
    "WS041": ("high", "mcp", "MCP server launch command differs from the pinned one"),
}


@dataclass(frozen=True, order=True)
class Finding:
    check: str
    path: str  # relative to the repository root, forward slashes
    line: int | None  # 1-based, when the finding points at a line
    message: str

    @property
    def severity(self) -> str:
        return CHECKS[self.check][0]

    @property
    def area(self) -> str:
        return CHECKS[self.check][1]

    def sort_key(self) -> tuple:
        return (SEVERITIES.index(self.severity), self.path, self.line or 0, self.check, self.message)


def finding(check: str, path: str, message: str, line: int | None = None) -> Finding:
    if check not in CHECKS:
        raise KeyError(f"unknown check {check!r}")
    return Finding(check, path, line, message)


def load_policy(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_json(path: Path) -> dict | None:
    """Parsed JSON, or None if the file does not exist. Invalid JSON raises ValueError."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_files(repo: Path, skip_dirs: list[str]) -> Iterator[Path]:
    """Every file under `repo`, sorted, skipping any directory named in `skip_dirs`."""
    for path in sorted(repo.rglob("*")):
        rel_parts = path.relative_to(repo).parts
        if any(part in skip_dirs for part in rel_parts[:-1]):
            continue
        if path.is_file():
            yield path


def read_text(path: Path, max_bytes: int = 1_000_000) -> str | None:
    """File contents as UTF-8 text, or None for binary, undecodable or oversized files."""
    if path.stat().st_size > max_bytes:
        return None
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def rel(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


def matches_any(name: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, g) for g in globs)


def markdown_sections(text: str) -> dict[str, str]:
    """Map each level-2 heading ("## Name") to the text under it, up to the next level-2 heading."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            current = m.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def redact(value: str) -> str:
    """Show only enough of a matched secret to find it: its first four characters."""
    return value[:4] + "…" if len(value) > 4 else "…"
