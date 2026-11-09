"""Characterization: relay.notify decides exactly as the legacy module did (PR notify-1; ADR-018).

The oracle is the legacy module itself, frozen in legacy_reference.py: for
every generated case, the frozen copy and relay.notify run on the same rows.
In notify-1 relay.notify is the same code, so every difference is a bug in
the harness; from notify-2 on, it is a change in behaviour. These tests pin
what the legacy code does, including behaviour nobody would choose today.
"""

import corpus
import legacy_reference as legacy
import pytest

import relay.notify as notify


def load(conn, states):
    for s in states:
        if s.row:
            conn.execute("INSERT INTO notification_prefs (user_id, muted_types, spam_marked_on) VALUES (?, ?, ?)",
                         (s.user_id, s.muted_types, s.spam_marked_on))
    conn.commit()


@pytest.fixture(scope="module")
def both():
    states = corpus.states()
    load(legacy.init(":memory:"), states)
    load(notify.init(":memory:"), states)
    return states, corpus.cases()


def test_the_corpus_is_the_size_the_chapter_quotes(both):
    states, cases = both
    assert (len(states), len(cases), len(corpus.sequences())) == (160, 5019, 40)


def test_every_decision_matches_the_legacy_module(both):
    _, cases = both
    differences = [(c.state.user_id, c.ntype, c.now, c.tags) for c in cases
                   if notify.should_send(c.state.user_id, c.ntype, c.now)
                   != legacy.should_send(c.state.user_id, c.ntype, c.now)]
    assert differences == []


def test_get_prefs_matches_the_legacy_module_exactly(both):
    states, _ = both
    assert [s.user_id for s in states if legacy.get_prefs(s.user_id) != notify.get_prefs(s.user_id)] == []


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
        decisions = [(t, n) for t in seq.checks for n in corpus.CASE_TYPES
                     if legacy.should_send(seq.user_id, n, t) != notify.should_send(seq.user_id, n, t)]
        if legacy.get_prefs(seq.user_id) != notify.get_prefs(seq.user_id) or decisions:
            differing.append((seq.user_id, decisions[:3]))
    assert differing == []
