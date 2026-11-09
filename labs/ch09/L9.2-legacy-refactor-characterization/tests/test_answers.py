"""Locks the arithmetic in book/answers/ch09-answers.md, Exercises 6 and 7 (Lab 9.2's functions)."""

from datetime import datetime

from modernize import migration, parallel
from modernize.paths import agent_module, oracle_modules, relay_notify

ROWS = [[1, "comment;mention", None], [2, "Digest", None], [3, None, "2026-12-01"], [4, "", "2026-12-05"],
        [5, "all;comment", "2026-11-20"]]


def test_exercise_6_losses_and_the_emails_that_follow():
    before = migration.before_prefs(ROWS, relay_notify().parse_muted)
    conn = migration.legacy_db(ROWS)
    agent = agent_module()
    agent.upgrade(conn)
    lost = migration.losses(before, migration.after_prefs(conn, before), False)
    assert (lost.optouts_before, lost.optouts_lost, lost.users_with_optouts_lost) == (5, 4, 2)
    assert (lost.spam_marks_before, lost.spam_marks_lost) == (3, 2)
    legacy, _ = oracle_modules()
    legacy_conn = legacy.init(":memory:")
    legacy_conn.executemany("INSERT INTO notification_prefs VALUES (?, ?, ?)", [tuple(r) for r in ROWS])
    legacy_conn.commit()
    agent._db = conn
    now = datetime(2026, 12, 9, 9, 0)
    newly_sent = [u for u in range(1, 6) if agent.should_send(u, "comment", now) and not legacy.should_send(
        u, "comment", now)]
    assert newly_sent == [1, 3, 4]


TASKS = [{"id": "A", "depends": [], "touches": ["a.py"]}, {"id": "B", "depends": ["A"], "touches": ["a.py", "b.py"]},
         {"id": "C", "depends": ["A"], "touches": ["c.py"]},
         {"id": "D", "depends": ["B", "C"], "touches": ["a.py", "d.py"]}, {"id": "E", "depends": ["A"], "touches": ["c.py"]}]


def test_exercise_7_waves_order_and_overlaps():
    assert parallel.waves(TASKS) == [["A"], ["B", "C", "E"], ["D"]]
    assert parallel.integration_order(TASKS) == ["A", "B", "C", "E", "D"]
    assert parallel.overlaps(TASKS) == [("C", "E", "c.py")]
