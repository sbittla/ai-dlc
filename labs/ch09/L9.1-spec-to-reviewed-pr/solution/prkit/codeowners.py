"""Who must review a path, from a CODEOWNERS file (provided).

GitHub's rule, which this follows for the patterns Relay uses: the last
matching line wins, and any one owner on that line can approve. `*` matches
every path; `/dir/` matches everything under it; `/file` matches one file.
Other glob forms are not used in Relay and are refused, so a new pattern
cannot be silently misread.
"""

from __future__ import annotations

from pathlib import Path


def parse(text: str) -> list[tuple[str, tuple[str, ...]]]:
    rules = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        if pattern != "*" and (not pattern.startswith("/") or any(c in pattern for c in "*?[")):
            raise ValueError(f"unsupported CODEOWNERS pattern {pattern!r}")
        rules.append((pattern, tuple(owners)))
    return rules


def load(repo: Path) -> list[tuple[str, tuple[str, ...]]]:
    return parse((repo / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))


def matches(pattern: str, path: str) -> bool:
    if pattern == "*":
        return True
    bare = pattern.lstrip("/")
    return path.startswith(bare) if bare.endswith("/") else path == bare


def owners_for(rules: list[tuple[str, tuple[str, ...]]], path: str) -> tuple[str, ...]:
    """The owners of the last matching rule, or () if none matches."""
    found: tuple[str, ...] = ()
    for pattern, owners in rules:
        if matches(pattern, path):
            found = owners
    return found
