"""A check for changes to agent instruction files (TODO 2 in starter/).

    INS001  hidden or reordering characters in added text
    INS002  an HTML comment added to an instruction file (invisible when rendered)
    INS003  a line of the Boundaries section removed or changed
    INS004  an instruction to fetch or run something from the network
    INS005  an instruction naming a package, library or package index to use
    INS006  an instruction to conceal, skip a control, or override other instructions
    INS007  an encoded blob (base64 or long hex) in added text
    INS008  a word mixing Latin letters with look-alike letters from another script (a homoglyph name)

It reads meaning only through patterns. A plain-language instruction that weakens a rule passes it, which is
why instruction files also have code owners who read for meaning.
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from dataclasses import dataclass

from .hidden import find_hidden, reveal_tags

INSTRUCTION_FILES = ["AGENTS.md", "*/AGENTS.md", "CLAUDE.md", "*/CLAUDE.md", "GEMINI.md", "*/GEMINI.md",
                     ".cursorrules", ".windsurfrules", ".cursor/rules/*", ".windsurf/rules/*",
                     ".github/copilot-instructions.md", ".github/instructions/*.instructions.md",
                     ".claude/skills/*/SKILL.md", ".claude/agents/*", ".claude/commands/*",
                     ".clinerules", ".clinerules/*", ".github/prompts/*.prompt.md",
                     # added 2026-11-11 (Appendix E, Section E.3): newer agent locations
                     "AGENTS.override.md", "*/AGENTS.override.md", "CLAUDE.local.md", "*/CLAUDE.local.md", ".claude/rules/*",
                     ".codex/*", ".agents/skills/*/SKILL.md", ".github/agents/*.agent.md",
                     ".github/skills/*/SKILL.md", ".github/hooks/*.json"]
NETWORK = re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr)\b|https?://", re.I)
PACKAGE = re.compile(r"(--(extra-)?index-url|\bpypi\b|\bregistry\b|\b(use|install|add) the `?[\w.-]+`? "
                     r"(package|library)\b|\bpackage\b.*\b(for|in) every\b)", re.I)
CONCEAL = re.compile(r"\b(do not|don't|never) (mention|tell|report|log|show)\b|\bignore (the |all |any )?(previous|"
                     r"prior|above|boundaries)\b|\bskip (review|tests?\b)|\bdisable (the )?(scan|scanning|scanner)"
                     r"|\bwithout (asking|review)\b", re.I)
BLOB = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}|\b[0-9a-f]{48,}\b")


@dataclass(frozen=True)
class Finding:
    rule: str
    line: int      # in the new file, 1-based; for INS003 the line in the old file
    message: str


def is_instruction_file(path: str) -> bool:
    """Provided: the paths agents read as instructions."""
    return any(fnmatch.fnmatch(path, pat) for pat in INSTRUCTION_FILES)


def added_lines(before: str, after: str) -> list[tuple[int, str]]:
    """Provided: (line number in `after`, text) for lines of `after` not present in `before`."""
    old = set(before.splitlines())
    return [(n, ln) for n, ln in enumerate(after.splitlines(), 1) if ln not in old]


def boundary_lines(text: str) -> list[tuple[int, str]]:
    """Provided: (line number, text) for the non-empty lines under '## Boundaries', up to the next heading."""
    out, inside = [], False
    for n, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("## "):
            inside = ln.strip() == "## Boundaries"
            continue
        if inside and ln.strip():
            out.append((n, ln))
    return out


def mixed_script_words(text: str) -> list[str]:
    """Provided: look-alike words. A word counts if it mixes ASCII letters with letters from another script
    (a Cyrillic 'у' in 'pyjwt'), or if NFKC folding changes it, as it does for fullwidth letters ('ｐyjwt').
    The script test runs on the folded word. Accented Latin letters do not count."""
    out = []
    for word in re.findall(r"[^\W\d_][\w.-]*", text):
        folded = unicodedata.normalize("NFKC", word)
        ascii_letters = any(c.isascii() and c.isalpha() for c in folded)
        other = any(c.isalpha() and not c.isascii() and "LATIN" not in unicodedata.name(c, "") for c in folded)
        if (ascii_letters and other) or folded != word:
            out.append(word)
    return out


def check_change(path: str, before: str, after: str) -> list[Finding]:
    """Findings for one change to one file; [] if the path is not an instruction file.

    For each added line (added_lines), in order, test INS001 (find_hidden on the line), INS002 ("<!--"),
    INS004 (NETWORK), INS005 (PACKAGE), INS006 (CONCEAL), INS007 (BLOB) and INS008 (mixed_script_words), at
    most one finding per rule per line, in that rule order. Run the text patterns on the line as reveal_tags
    decodes it (tag characters and variation-selector runs become text), with hidden characters removed, so
    smuggled text is judged too. Then INS003: one finding for each
    Boundaries line of `before` that is not among the Boundaries lines of `after`, with the old line number.
    Messages are free text.
    """
    raise NotImplementedError("TODO 2: the instruction-file check INS001-INS008")
