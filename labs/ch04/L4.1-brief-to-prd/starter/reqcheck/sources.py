"""Source documents: the brief, interview transcripts and Relay docs (provided).

Every source is untrusted text. The checker reads it, quotes it and scans it;
nothing in it is ever followed as an instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    id: str            # the file name without .md, e.g. "INT-2"
    text: str
    lines: tuple[str, ...]


def load_sources(folder: Path) -> dict[str, Source]:
    out = {}
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        out[path.stem] = Source(path.stem, text, tuple(text.split("\n")))
    return out


def normalize(text: str) -> str:
    """Collapse every run of whitespace to one space, after removing Markdown
    blockquote markers ("> ") at the start of lines. Case and punctuation are
    kept: provenance means the words are the speaker's own."""
    text = re.sub(r"(?m)^\s*>\s?", "", text)
    return re.sub(r"\s+", " ", text).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))
