"""Locks the arithmetic in book/answers/ch09-answers.md, Exercise 5 (Lab 9.1's pre-review check)."""

from prkit import prcheck


def f(path, status, added, removed):
    return {"path": path, "status": status, "added": added, "removed": removed}


def record(commits, minutes):
    return {"review": {"minutes": minutes}, "description": "Refactor the escalation summary.",
            "commits": [{"author": "x", "message": "m", "files": c} for c in commits]}


TESTS = [f("tests/test_x.py", "A", 120, 0)]
CODE = [f("src/relay/a.py", "M", 150, 30), f("tests/test_old.py", "M", 10, 4)]


def codes(r):
    return [x.code for x in prcheck.check_pr(r)]


def test_exercise_5_as_given():
    r = record([TESTS, CODE], 40)
    assert prcheck.sizes(r) == (180, 314)
    assert codes(r) == ["PR02", "PR09"]  # 314 lines in 40 minutes is 471 an hour: no PR08


def test_exercise_5a_a_30_minute_review():
    assert codes(record([TESTS, CODE], 30)) == ["PR02", "PR08", "PR09"]  # 628 an hour


def test_exercise_5b_the_test_change_moved_into_the_first_commit():
    r = record([TESTS + [CODE[1]], [CODE[0]]], 40)
    assert prcheck.sizes(r) == (180, 314) and codes(r) == ["PR09"]
