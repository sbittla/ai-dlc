"""The arithmetic behind book/answers/ch17-answers.md, Exercise 5 (Lab 17.1's relay-repo)."""

import perflab  # noqa: F401  (puts relay-repo/src on the path)
from relay.service.sharedlimit import SharedRateLimiter


def test_exercise_5_four_processes(tmp_path):
    db = str(tmp_path / "r.db")
    lims = [SharedRateLimiter(db) for _ in range(4)]
    assert (4 - 1) * (10 - 1) == 27                                   # (a) the early-refusal bound
    assert sum(lims[i % 4].check("k", 10.0)[0] for i in range(600)) == 600
    assert sum(lim.transactions for lim in lims) == 60                # (b) 150 per process, 15 leases each
    # the bound is reached when three processes each hold 9 unused counts
    a, b, c, d = [SharedRateLimiter(str(tmp_path / "s.db")) for _ in range(4)]
    for lim in (a, b, c):
        assert lim.check("k", 20.0)[0]                                 # each leases 10, uses 1
    served = 3 + sum(d.check("k", 20.0)[0] for _ in range(1000))
    assert served == 600 - 27
