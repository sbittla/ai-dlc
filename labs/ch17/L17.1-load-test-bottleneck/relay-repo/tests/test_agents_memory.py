"""Compaction that keeps pinned messages, and reviewed long-term memory with provenance (4.24.0, ADR-026)."""

import sqlite3

import pytest

from relay.agents.memory import MemoryRefused, MemoryStore, Message, compact

TASK = Message("user", "Task HT-031; edit only rules.py; approved tests are fixed", 300, pinned=True)


def summary(old):
    return Message("summary", f"summary of {len(old)} messages", 200)


def history(n, tokens=1000):
    return [TASK] + [Message("tool", f"result {i}", tokens) for i in range(n)]


def test_a_context_that_fits_is_unchanged():
    c = compact(history(3), 10_000, keep_last=2, summarize=summary)
    assert c.dropped == 0 and c.tokens_after == 3300


def test_old_messages_become_one_summary_and_the_pinned_task_survives():
    c = compact(history(10), 4_000, keep_last=3, summarize=summary)
    assert c.messages[0] == TASK and c.messages[1].role == "summary"
    assert [m.text for m in c.messages[2:]] == ["result 7", "result 8", "result 9"]
    assert (c.dropped, c.tokens_before, c.tokens_after) == (7, 10_300, 3_500)  # 300 + 200 + 3 x 1,000


def test_compaction_that_cannot_fit_stops_instead_of_dropping_the_pin():
    with pytest.raises(ValueError):
        compact(history(10), 3_000, keep_last=3, summarize=summary)


def memory():
    t = [1000.0]
    return MemoryStore(sqlite3.connect(":memory:"), frozenset({"priya.n", "sam.o"}), lambda: t[0]), t


def test_a_proposed_fact_is_not_recalled_until_a_person_accepts_it():
    m, _ = memory()
    i = m.propose("rules.py", "validate_rule takes a project ID", "src/relay/escalation/rules.py", "run-1",
                  "spec-to-pr-helper")
    assert m.recall("rules.py") == []
    m.review(i, "priya.n", True)
    got = m.recall("rules.py")
    assert got[0]["fact"] == "validate_rule takes a project ID" and got[0]["reviewed_by"] == "priya.n"
    assert got[0]["source"] == "src/relay/escalation/rules.py" and got[0]["proposed_by"] == "spec-to-pr-helper"


def test_an_agent_cannot_review_and_a_fact_needs_a_source():
    m, _ = memory()
    i = m.propose("rules.py", "x", "a.py", "run-1", "spec-to-pr-helper")
    with pytest.raises(MemoryRefused):
        m.review(i, "spec-to-pr-helper", True)
    with pytest.raises(MemoryRefused):
        m.propose("rules.py", "y", "", "run-1", "spec-to-pr-helper")


def test_a_review_happens_once_for_a_known_fact_and_is_audited():
    from relay.audit import AuditTrail
    trail = AuditTrail(clock=lambda: "t")
    m = MemoryStore(sqlite3.connect(":memory:"), frozenset({"sam.o"}), lambda: 0.0, trail)
    i = m.propose("t", "x", "a.py", "run-1", "spec-to-pr-helper")
    m.review(i, "sam.o", True)
    with pytest.raises(MemoryRefused):
        m.review(i, "sam.o", False)
    with pytest.raises(MemoryRefused):
        m.review(999, "sam.o", True)
    assert [(r["action"], r["outcome"]) for r in trail.records] == [("memory.review", "accepted")]


def test_rejected_and_expired_facts_are_not_recalled():
    m, t = memory()
    a = m.propose("t", "planted", "README.md", "run-1", "spec-to-pr-helper")
    m.review(a, "sam.o", False)
    b = m.propose("t", "true for now", "x.py", "run-2", "spec-to-pr-helper", ttl_days=1)
    m.review(b, "sam.o", True)
    assert [r["fact"] for r in m.recall("t")] == ["true for now"]
    t[0] += 2 * 86400
    assert m.recall("t") == []
