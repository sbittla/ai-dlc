"""The shared rate limiter (4.21.0, ADR-014; leases 4.28.0, ADR-041): one count per token, however many processes."""

import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from relay.service.ratelimit import RateLimiter
from relay.service.sharedlimit import LEASE_BLOCK, SharedRateLimiter

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


def test_two_exact_limiters_on_one_database_share_the_count(tmp_path):
    db = str(tmp_path / "r.db")
    a, b = SharedRateLimiter(db, limit=3, block=1), SharedRateLimiter(db, limit=3, block=1)
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


# ---------------------------------------------------------------- leases (4.28.0, ADR-041)

def test_the_default_lease_is_ten_counts():
    assert LEASE_BLOCK == 10


@pytest.mark.parametrize("seed", range(5))
def test_one_process_decides_exactly_as_the_exact_limiter(tmp_path, seed):
    rng = random.Random(seed)
    leased = SharedRateLimiter(str(tmp_path / "a.db"), limit=7)
    exact = SharedRateLimiter(str(tmp_path / "b.db"), limit=7, block=1)
    t = 0.0
    for _ in range(400):
        t += rng.choice((0.1, 0.5, 2.0, 9.0))
        key = rng.choice("abc")
        assert leased.check(key, t) == exact.check(key, t)


def test_a_lease_costs_one_transaction_for_ten_requests(tmp_path):
    exact = SharedRateLimiter(str(tmp_path / "a.db"), block=1)
    leased = SharedRateLimiter(str(tmp_path / "b.db"))
    for i in range(100):
        exact.check("k", 30.0 + i * 0.01)
        leased.check("k", 30.0 + i * 0.01)
    assert (exact.transactions, leased.transactions) == (100, 10)


def test_a_token_past_its_limit_causes_no_more_writes(tmp_path):
    lim = SharedRateLimiter(str(tmp_path / "r.db"), limit=20)
    assert sum(lim.check("k", 1.0)[0] for _ in range(1000)) == 20
    assert lim.transactions == 3  # two leases of 10, one that finds the window full; the other 979 cost nothing
    assert lim.check("k", 61.0) == (True, 0)  # a new window leases again


def test_processes_never_admit_more_than_the_limit_and_refuse_early_by_at_most_block_minus_one(tmp_path):
    db = str(tmp_path / "r.db")
    a, b = SharedRateLimiter(db, limit=600), SharedRateLimiter(db, limit=600)
    allowed_a = sum(a.check("k", 10.0)[0] for _ in range(595))  # a leases 600 and keeps 5 unused
    assert allowed_a == 595
    allowed_b = sum(b.check("k", 11.0)[0] for _ in range(50))
    assert allowed_b == 0  # the window is fully leased: b is refused although only 595 requests were served
    assert 600 - (allowed_a + allowed_b) <= LEASE_BLOCK - 1


def test_alternating_processes_admit_exactly_the_limit(tmp_path):
    db = str(tmp_path / "r.db")
    a, b = SharedRateLimiter(db, limit=600), SharedRateLimiter(db, limit=600)
    allowed = sum(lim.check("k", 20.0)[0] for _ in range(400) for lim in (a, b))
    assert allowed == 600


def test_block_and_limit_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        SharedRateLimiter(str(tmp_path / "r.db"), block=0)
