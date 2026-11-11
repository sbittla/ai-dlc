"""Characterization: the new notification code decides exactly as the legacy module did (PR notify-1; ADR-018).

The oracle is the legacy module itself, unchanged, in legacy_reference.py: for
every generated case the legacy `should_send` and `get_prefs` are run on the
legacy table, and the new code on the new tables filled by `migrate_legacy`.
These tests pin what the legacy code does, including behaviour nobody would
choose today; they do not say it is right.

One difference is accepted, and listed here so a reviewer sees it: the new
`get_prefs` lists muted types sorted and without duplicates (ADR-018,
accepted by lena.k on 2026-12-15). Every other difference fails.
"""

import corpus
import legacy_reference as legacy
import pytest

import relay.notify as notify

ACCEPTED = {"get_prefs": "order_or_duplicates"}


def load(conn, states):
    for s in states:
        if s.row:
            conn.execute("INSERT INTO notification_prefs (user_id, muted_types, spam_marked_on) VALUES (?, ?, ?)",
                         (s.user_id, s.muted_types, s.spam_marked_on))


@pytest.fixture(scope="module")
def both():
    states = corpus.states()
    load(legacy.init(":memory:"), states)
    legacy._db.commit()
    store = notify.init(":memory:")
    load(store.conn, states)
    notify.migrate_legacy(store)
    return states, corpus.cases()


def classify_prefs(old: dict, new: dict) -> str | None:
    if old == new:
        return None
    same = old["spam_marked_on"] == new["spam_marked_on"] and set(old["muted"]) == set(new["muted"])
    return "order_or_duplicates" if same else "content"


def test_the_corpus_is_the_size_the_chapter_quotes(both):
    states, cases = both
    assert (len(states), len(cases), len(corpus.sequences())) == (160, 5019, 40)


def test_every_decision_matches_the_legacy_module(both):
    _, cases = both
    differences = [(c.state.user_id, c.ntype, c.now, c.tags) for c in cases
                   if notify.should_send(c.state.user_id, c.ntype, c.now)
                   != legacy.should_send(c.state.user_id, c.ntype, c.now)]
    assert differences == []


def test_get_prefs_differs_only_in_the_accepted_way(both):
    states, _ = both
    kinds = {classify_prefs(legacy.get_prefs(s.user_id), notify.get_prefs(s.user_id)) for s in states}
    assert kinds - {None} <= {ACCEPTED["get_prefs"]}


def test_the_corpus_exercises_every_quirk_the_review_named(both):
    _, cases = both
    seen = {t for c in cases for t in c.tags}
    assert {"no_row", "semicolon_list", "mixed_case", "muted_all", "spam_mark", "spam_without_muted",
            "spam_boundary", "security", "unknown_type", "aware_time"} <= seen


def test_write_sequences_leave_the_same_preferences_and_decisions(both):
    """mute, mark_spam and clear_spam through both modules, then every type decided at naive and aware times."""
    differing = []
    for seq in corpus.sequences():
        corpus.apply(legacy, seq)
        corpus.apply(notify, seq)
        prefs = classify_prefs(legacy.get_prefs(seq.user_id), notify.get_prefs(seq.user_id))
        decisions = [(t, n) for t in seq.checks for n in corpus.CASE_TYPES
                     if legacy.should_send(seq.user_id, n, t) != notify.should_send(seq.user_id, n, t)]
        if prefs not in (None, ACCEPTED["get_prefs"]) or decisions:
            differing.append((seq.user_id, prefs, decisions[:3]))
    assert differing == []
