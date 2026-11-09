"""The shared rate limiter (4.21.0, ADR-014): one count per token, however many processes serve requests."""

import os
import subprocess
import sys
from pathlib import Path

from relay.service.ratelimit import RateLimiter
from relay.service.sharedlimit import SharedRateLimiter

SRC = Path(__file__).resolve().parent.parent / "src"


def test_same_window_rule_as_the_in_process_limiter(tmp_path):
    shared, local = SharedRateLimiter(str(tmp_path / "r.db"), limit=3), RateLimiter(limit=3)
    times = [0.0, 1.0, 2.0, 30.5, 59.9, 60.0, 61.0]
    assert [shared.check("k", t) for t in times] == [local.check("k", t) for t in times]
    assert [shared.check("k", t)[0] for t in (62.0,)] == [True]


def test_refusal_gives_seconds_until_the_window_ends(tmp_path):
    lim = SharedRateLimiter(str(tmp_path / "r.db"), limit=1)
    assert lim.check("k", 120.0) == (True, 0)
    assert lim.check("k", 150.2) == (False, 30)


def test_two_limiters_on_one_database_share_the_count(tmp_path):
    db = str(tmp_path / "r.db")
    a, b = SharedRateLimiter(db, limit=3), SharedRateLimiter(db, limit=3)
    results = [a.check("k", 10.0)[0], b.check("k", 11.0)[0], a.check("k", 12.0)[0], b.check("k", 13.0)[0]]
    assert results == [True, True, True, False]


def test_tokens_are_counted_separately(tmp_path):
    lim = SharedRateLimiter(str(tmp_path / "r.db"), limit=1)
    assert [lim.check("a", 5.0)[0], lim.check("b", 5.0)[0], lim.check("a", 6.0)[0]] == [True, True, False]


def test_old_windows_are_removed(tmp_path):
    lim = SharedRateLimiter(str(tmp_path / "r.db"), limit=5)
    for t in (0.0, 60.0, 120.0):
        lim.check("k", t)
    assert lim.conn.execute("SELECT window_start FROM rate_limit_windows").fetchall() == [(120,)]


def test_two_processes_allow_600_between_them_not_1200(tmp_path):
    db = str(tmp_path / "r.db")
    SharedRateLimiter(db).close()  # create the table before the race
    code = ("import sys; from relay.service.sharedlimit import SharedRateLimiter as S; "
            "s = S(sys.argv[1]); print(sum(s.check('k', 30.0)[0] for _ in range(400)))")
    env = dict(os.environ, PYTHONPATH=str(SRC))
    procs = [subprocess.Popen([sys.executable, "-c", code, db], stdout=subprocess.PIPE, text=True, env=env)
             for _ in range(2)]
    allowed = [int(p.communicate(timeout=120)[0]) for p in procs]
    assert sum(allowed) == 600
