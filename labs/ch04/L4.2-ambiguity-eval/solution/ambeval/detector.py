"""A rule-based defect detector: the baseline any model must beat (reference solution).

One function is a TODO in starter/: detect_missing_actor. The others are provided.
Every rule is deliberately simple and readable, so that each miss and each false
alarm can be explained by pointing at a word.
"""

from __future__ import annotations

import re

from .data import Lexicon, Statement

STOPWORDS = frozenset("""a an the and or of to in on for by with at from as is are be been must can
not no only each every any its it this that their they when if than then per one""".split())


def term_pattern(term: str, ignore_case: bool = True) -> re.Pattern:
    """Whole word or phrase: not preceded or followed by a letter or digit (as in Lab 4.1)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
                      re.IGNORECASE if ignore_case else 0)


def has_any(text: str, terms: tuple[str, ...], ignore_case: bool = True) -> bool:
    return any(term_pattern(t, ignore_case).search(text) for t in terms)


def is_measurable(text: str, lexicon: Lexicon) -> bool:
    return any(re.search(p, text) for p in lexicon.measurable_patterns)


def detect_ambiguity(text: str, lexicon: Lexicon) -> bool:
    """A vague term occurs."""
    return has_any(text, lexicon.vague_terms)


def detect_untestable(text: str, lexicon: Lexicon) -> bool:
    """A weak modal occurs, or the statement has no measurable threshold and makes
    a quality claim (a vague term or a quality term such as 'reliably')."""
    if has_any(text, lexicon.weak_modals):
        return True
    return not is_measurable(text, lexicon) and (has_any(text, lexicon.vague_terms)
                                                 or has_any(text, lexicon.quality_terms))


# ------------------------------------------------------------------ TODO

def detect_missing_actor(text: str, lexicon: Lexicon) -> bool:
    """True when the statement uses a passive verb and names no actor.

    - "Passive" means lexicon.passive_pattern matches the text (for example
      "is sent", "be retried", "are logged").
    - "Names an actor" means any of lexicon.actor_terms occurs as a whole word,
      matched case-sensitively (so "Relay" and "Admin" count, "relay race" does
      not), or the text contains the word "by" followed by another word
      ("by the Owner", "by Admins").
    A statement with no passive verb is never flagged, even if it names nobody:
    that is a known limit of this rule, and the eval measures what it costs.
    """
    if not re.search(lexicon.passive_pattern, text):
        return False
    if has_any(text, lexicon.actor_terms, ignore_case=False):
        return False
    return not re.search(r"(?i)\bby\s+\w", text)


# ------------------------------------------------------------------ provided

def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z'-]*", text.lower())
    return {w for w in words if w not in STOPWORDS}


def numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def negated(text: str) -> bool:
    return bool(re.search(r"(?i)\b(must not|cannot|can't|never)\b", text))


def detect_contradictions(statements: list[Statement], lexicon: Lexicon) -> set[str]:
    """Ids of statements that look as if they conflict with another in the same set.

    Two statements in a set conflict if their content words overlap (Jaccard) by at
    least min_overlap and both contain numbers that differ, or overlap by at least
    min_overlap_polarity and exactly one of them is negated."""
    flagged: set[str] = set()
    by_set: dict[str, list[Statement]] = {}
    for s in statements:
        by_set.setdefault(s.set, []).append(s)
    for group in by_set.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                wa, wb = content_words(a.text), content_words(b.text)
                overlap = len(wa & wb) / len(wa | wb) if wa | wb else 0.0
                na, nb = numbers(a.text), numbers(b.text)
                if overlap >= lexicon.min_overlap and na and nb and na != nb:
                    flagged |= {a.id, b.id}
                elif overlap >= lexicon.min_overlap_polarity and negated(a.text) != negated(b.text):
                    flagged |= {a.id, b.id}
    return flagged


def predict(statements: list[Statement], lexicon: Lexicon) -> dict[str, frozenset[str]]:
    """Predicted defect types for every statement."""
    conflicts = detect_contradictions(statements, lexicon)
    out = {}
    for s in statements:
        found = set()
        if detect_ambiguity(s.text, lexicon):
            found.add("ambiguity")
        if detect_untestable(s.text, lexicon):
            found.add("untestable")
        if s.id in conflicts:
            found.add("contradiction")
        if detect_missing_actor(s.text, lexicon):
            found.add("missing_actor")
        out[s.id] = frozenset(found)
    return out
