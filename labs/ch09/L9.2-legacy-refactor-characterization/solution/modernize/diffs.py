"""Changed lines between two versions of a file, counted as a review tool counts them (provided)."""

from __future__ import annotations

import difflib


def changed_lines(old: str | None, new: str | None) -> int:
    """Added plus removed lines in a unified diff with no context; 0 if equal. None means the file is absent."""
    if old == new:
        return 0
    a = [] if old is None else old.splitlines()
    b = [] if new is None else new.splitlines()
    return sum(1 for line in difflib.unified_diff(a, b, lineterm="", n=0)
               if line[:1] in "+-" and not line.startswith(("+++", "---")))
