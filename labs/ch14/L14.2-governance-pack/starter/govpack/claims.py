"""Find claims in a governance text that the evidence cannot support (starter: TODOs).

Evidence can show that a control exists, was tested, or maps to a framework's clause. It cannot make a
product "compliant", "certified" or "secure", and a classification is a reading, not a settled fact. The
checker flags the phrases below; a sentence that negates (contains "not" or "no" as a word) is exempt,
so "this is not a compliance claim" passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OVERCLAIMS = (
    r"\b(?:fully )?compliant\b",
    r"\bcertified\b",
    r"\bguarantee[sd]?\b",
    r"\bmeets all requirements\b",
    r"\bsecure by design\b",
    r"\b100% secure\b",
    r"\b(?:is|are) (?:minimal|limited|high)[- ]risk\b",
)


@dataclass(frozen=True)
class Overclaim:
    line: int
    phrase: str
    sentence: str


def find_overclaims(text: str) -> list[Overclaim]:
    """Every overclaim, in text order: (line number from 1, the matched phrase as written, the sentence).

    Split each line into sentences at ". ", "? " or "! " (keep it simple: no abbreviations to handle). Skip
    heading lines (starting with "#"). Skip any sentence containing the word "not" or "no" (case-insensitive).
    Within a sentence, report every match of every pattern in OVERCLAIMS, ordered by position.
    """
    raise NotImplementedError("TODO 4: find overclaims")
