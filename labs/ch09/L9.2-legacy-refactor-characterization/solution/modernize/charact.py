"""Characterization: run a candidate and the legacy module on the same cases, and report every difference.

A candidate is any module with the legacy module's public functions: `init`,
`should_send` and `get_prefs`. Both get the same stored rows. A candidate
that keeps its data in new tables is migrated first, by its own migration
(`migrate` or `migrate_legacy`), exactly as it would be in production; so a
migration that loses rows shows up here as decisions that differ.

Differences are grouped by the case's tags (corpus.tags_for), so a report
says which behaviour changed, not just how many cases did.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Result:
    cases: int
    decision_differences: int
    by_tag: Counter = field(default_factory=Counter)  # tag -> differing cases with that tag
    prefs: Counter = field(default_factory=Counter)  # class -> users whose get_prefs differs
    unaccepted_prefs: int = 0
    shadow_differences: int = 0  # recorded by a candidate reading in shadow mode
    write_sequences: int | None = None  # None: the candidate has no write functions to characterize
    write_differences: int = 0  # sequences after which reads or decisions differ (accepted classes aside)


def load(conn, states) -> None:
    """Insert each state's raw row into the legacy table, as production stored it."""
    for s in states:
        if s.row:
            conn.execute("INSERT INTO notification_prefs (user_id, muted_types, spam_marked_on) VALUES (?, ?, ?)",
                         (s.user_id, s.muted_types, s.spam_marked_on))
    conn.commit()


def prepare(candidate, states) -> object:
    """init the candidate, load the rows, and run its own migration if it has one. Returns what init returned."""
    handle = candidate.init(":memory:")
    load(getattr(handle, "conn", handle), states)
    if hasattr(candidate, "migrate_legacy") and hasattr(handle, "conn"):
        candidate.migrate_legacy(handle)
    elif hasattr(candidate, "migrate"):
        candidate.migrate()
    return handle


def compare_decisions(cases, old_send, new_send) -> tuple[int, Counter]:
    """(number of cases where new_send differs from old_send, Counter of the differing cases' tags).

    `old_send` and `new_send` are callables (user_id, ntype, now) -> bool. A call
    to `new_send` that raises counts as a difference: an error is not the legacy
    answer. A case with no tags counts under "untagged", so no difference goes
    unreported.
    """
    differing, by_tag = 0, Counter()
    for c in cases:
        try:
            new = new_send(c.state.user_id, c.ntype, c.now)
        except Exception as exc:  # noqa: BLE001 - recorded as a difference, never hidden
            new = f"raised {type(exc).__name__}"
        if new != old_send(c.state.user_id, c.ntype, c.now):
            differing += 1
            by_tag.update(c.tags or ("untagged",))
    return differing, by_tag


def classify_prefs(old: dict, new: dict) -> str | None:
    """None if equal; "order_or_duplicates" if only the muted list's order or duplicates differ; else "content"."""
    if old == new:
        return None
    same = old["spam_marked_on"] == new["spam_marked_on"] and set(old["muted"]) == set(new["muted"])
    return "order_or_duplicates" if same else "content"


def characterize(candidate, legacy, corpus, accepted: set[str] = frozenset()) -> Result:
    """Compare `candidate` with `legacy` on every case in `corpus`; `accepted` holds accepted get_prefs classes."""
    states, cases = corpus.states(), corpus.cases()
    load(legacy.init(":memory:"), states)
    handle = prepare(candidate, states)
    differing, by_tag = compare_decisions(cases, legacy.should_send, candidate.should_send)
    prefs = Counter(k for s in states if (k := classify_prefs(legacy.get_prefs(s.user_id),
                                                             candidate.get_prefs(s.user_id))) is not None)
    shadow = len(getattr(handle, "shadow_differences", ()))
    result = Result(len(cases), differing, by_tag, prefs, sum(n for k, n in prefs.items() if k not in accepted), shadow)
    if all(hasattr(candidate, f) for f in ("mute", "mark_spam", "clear_spam")):
        result.write_sequences, result.write_differences = characterize_writes(candidate, legacy, corpus, accepted)
    return result


def characterize_writes(candidate, legacy, corpus, accepted: set[str] = frozenset()) -> tuple[int, int]:
    """(sequences, sequences that differ): apply each write sequence to both, then compare reads and decisions.

    Call after `characterize`, which has initialized both modules. Sequences use their own user IDs.
    """
    differing = 0
    for seq in corpus.sequences():
        corpus.apply(legacy, seq)
        corpus.apply(candidate, seq)
        kind = classify_prefs(legacy.get_prefs(seq.user_id), candidate.get_prefs(seq.user_id))
        decided = [(t, n) for t in seq.checks for n in corpus.CASE_TYPES
                   if legacy.should_send(seq.user_id, n, t) != candidate.should_send(seq.user_id, n, t)]
        differing += bool(decided) or (kind is not None and kind not in accepted)
    return len(corpus.sequences()), differing
