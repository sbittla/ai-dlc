"""Changed lines between two versions of a file (provided).

A changed line is one added or one removed line in a unified diff with no
context, which is how most review tools count a pull request's size. A
modified line therefore counts twice: once removed, once added.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileChange:
    path: str
    status: str  # A added, M modified, D deleted
    added: int
    removed: int
    added_lines: tuple[str, ...] = field(default=(), repr=False)
    removed_lines: tuple[str, ...] = field(default=(), repr=False)

    @property
    def changed(self) -> int:
        return self.added + self.removed


def change(path: str, old: str | None, new: str | None) -> FileChange | None:
    """The change from `old` to `new` (None for a file that does not exist), or None if they are equal."""
    if old == new:
        return None
    a = [] if old is None else old.splitlines()
    b = [] if new is None else new.splitlines()
    added, removed = [], []
    for line in difflib.unified_diff(a, b, lineterm="", n=0):
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    status = "A" if old is None else "D" if new is None else "M"
    return FileChange(path, status, len(added), len(removed), tuple(added), tuple(removed))


def from_record(entry: dict) -> FileChange:
    """A FileChange from a pull-request record's file entry (counts, and optional excerpts of lines)."""
    return FileChange(entry["path"], entry["status"], entry["added"], entry["removed"],
                      tuple(entry.get("added_lines", ())), tuple(entry.get("removed_lines", ())))
