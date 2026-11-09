"""Characterization, migration losses, integration order and the three-way merge, on inputs you can check by hand."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import pytest

from modernize import charact, migration, parallel
from modernize.merge import merge3


@dataclass(frozen=True)
class S:
    user_id: int


@dataclass(frozen=True)
class C:
    state: S
    ntype: str
    now: datetime
    tags: tuple


NOW = datetime(2026, 12, 9, 8, 0)
CASES = [C(S(1), "comment", NOW, ("semicolon_list",)), C(S(1), "security", NOW, ("security", "spam_mark")),
         C(S(2), "digest", NOW, ()), C(S(3), "mention", NOW, ("no_row",))]


def test_compare_decisions_counts_differences_and_their_tags():
    old = {(1, "comment"): False, (1, "security"): False, (2, "digest"): True, (3, "mention"): True}
    new = {(1, "comment"): True, (1, "security"): True, (2, "digest"): False, (3, "mention"): True}
    n, tags = charact.compare_decisions(CASES, lambda u, t, _: old[(u, t)], lambda u, t, _: new[(u, t)])
    assert n == 3
    assert tags == Counter({"semicolon_list": 1, "security": 1, "spam_mark": 1, "untagged": 1})


def test_compare_decisions_finds_nothing_when_the_candidate_agrees():
    assert charact.compare_decisions(CASES, lambda *a: True, lambda *a: True) == (0, Counter())


@pytest.mark.parametrize("old, new, expected", [
    ({"muted": ["comment"], "spam_marked_on": None}, {"muted": ["comment"], "spam_marked_on": None}, None),
    ({"muted": ["mention", "comment", "comment"], "spam_marked_on": None},
     {"muted": ["comment", "mention"], "spam_marked_on": None}, "order_or_duplicates"),
    ({"muted": ["comment;mention"], "spam_marked_on": None},
     {"muted": ["comment", "mention"], "spam_marked_on": None}, "content"),
    ({"muted": [], "spam_marked_on": "2026-12-01"}, {"muted": [], "spam_marked_on": None}, "content"),
])
def test_classify_prefs(old, new, expected):
    assert charact.classify_prefs(old, new) == expected


def test_losses_counts_pairs_users_and_spam_marks():
    before = {1: (frozenset({"comment", "mention"}), None), 2: (frozenset(), "2026-12-01"),
              3: (frozenset({"digest"}), "2026-11-20")}
    after = {1: (frozenset({"comment;mention"}), None), 2: (frozenset(), None),
             3: (frozenset({"digest"}), "2026-11-20")}
    assert migration.losses(before, after, False) == migration.Losses(
        users=3, optouts_before=3, optouts_after=2, optouts_lost=2, users_with_optouts_lost=1,
        spam_marks_before=2, spam_marks_lost=1, legacy_table_kept=False)


def test_the_incidents_migration_on_four_rows_loses_what_the_chapter_says(tmp_path):
    from modernize.paths import agent_module, relay_notify

    rows = [[1001, "comment;mention", None], [1002, None, "2026-12-01"], [1003, "digest,due_soon", "2026-11-20"],
            [1004, "", None]]
    before = migration.before_prefs(rows, relay_notify().parse_muted)
    conn = migration.legacy_db(rows)
    agent_module().upgrade(conn)
    lost = migration.losses(before, migration.after_prefs(conn, before), migration.table_exists(conn,
                                                                                                "notification_prefs"))
    assert (lost.optouts_lost, lost.users_with_optouts_lost, lost.spam_marks_lost, lost.legacy_table_kept) == (
        2, 1, 1, False)


TASKS = [{"id": "A", "depends": [], "touches": ["x.py"]}, {"id": "C", "depends": ["A"], "touches": ["y.py"]},
         {"id": "B", "depends": ["A"], "touches": ["x.py", "z.py"]}, {"id": "D", "depends": ["B", "C"], "touches": []}]


def test_integration_order_follows_dependencies_then_ids():
    assert parallel.integration_order(TASKS) == ["A", "B", "C", "D"]
    assert parallel.waves(TASKS) == [["A"], ["B", "C"], ["D"]]


@pytest.mark.parametrize("tasks", [
    [{"id": "A", "depends": ["B"], "touches": []}, {"id": "B", "depends": ["A"], "touches": []}],
    [{"id": "A", "depends": ["Z"], "touches": []}],
])
def test_a_cycle_or_an_unknown_dependency_is_refused(tasks):
    with pytest.raises(ValueError):
        parallel.integration_order(tasks)


def test_overlaps_are_files_two_tasks_in_one_wave_both_touch():
    tasks = TASKS + [{"id": "E", "depends": ["A"], "touches": ["y.py"]}]
    assert parallel.overlaps(tasks) == [("C", "E", "y.py")]


BASE = "a\nb\nc\nd\n"


def test_merge3_applies_changes_to_different_lines():
    assert merge3(BASE, "A\nb\nc\nd\n", "a\nb\nc\nD\n").text == "A\nb\nc\nD\n"


def test_merge3_reports_changes_to_the_same_line_as_a_conflict():
    result = merge3(BASE, "a\nB1\nc\nd\n", "a\nB2\nc\nd\n")
    assert (result.text, result.conflicts) == (None, ((2, 2),))


def test_merge3_treats_two_insertions_at_one_point_as_a_conflict_and_identical_changes_as_one():
    assert merge3(BASE, "a\nx\nb\nc\nd\n", "a\ny\nb\nc\nd\n").text is None
    assert merge3(BASE, "a\nx\nb\nc\nd\n", "a\nx\nb\nc\nd\n").text == "a\nx\nb\nc\nd\n"


def test_on_the_prod_like_data_every_lost_optout_was_a_semicolon_list_and_every_lost_mark_had_no_list():
    """The chapter's account of the incident's two bugs, checked on the replayed data."""
    from modernize.paths import DATA, agent_module, relay_notify

    rows = migration.load_prod(DATA)["rows"]
    before = migration.before_prefs(rows, relay_notify().parse_muted)
    conn = migration.legacy_db(rows)
    agent_module().upgrade(conn)
    after = migration.after_prefs(conn, before)
    raw = {uid: muted for uid, muted, _ in rows}
    lost_pairs = {(u, t) for u, (m, _) in before.items() for t in m} - {(u, t) for u, (m, _) in after.items() for t in m}
    lost_marks = [u for u, (_, spam) in before.items() if spam and after[u][1] != spam]
    assert lost_pairs and all(";" in raw[u] for u, _ in lost_pairs)
    assert lost_marks and all(raw[u] in (None, "") for u in lost_marks)


def test_a_candidate_that_raises_counts_as_a_difference():
    def broken(u, t, now):
        raise TypeError("can't subtract offset-naive and offset-aware datetimes")

    n, tags = charact.compare_decisions(CASES[:2], lambda *a: True, broken)
    assert (n, tags) == (2, Counter({"semicolon_list": 1, "security": 1, "spam_mark": 1}))


def test_the_rewrite_raises_on_an_aware_time_for_a_spam_marked_user():
    """Why Table 9.7's aware_time row is large for the rewrite: it subtracts a naive mark from an aware time."""
    from datetime import timedelta, timezone

    from modernize.paths import agent_module

    agent = agent_module()
    conn = agent.init(":memory:")
    conn.execute("INSERT INTO notification_prefs VALUES (1, NULL, '2026-12-01')")
    conn.execute("INSERT INTO notification_prefs VALUES (2, 'x', '2026-12-01')")
    agent.migrate()
    with pytest.raises(TypeError):
        agent.should_send(2, "comment", datetime(2026, 12, 9, 8, 0, tzinfo=timezone(timedelta(hours=14))))
