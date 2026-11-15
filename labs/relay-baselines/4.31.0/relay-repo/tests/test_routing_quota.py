"""relay.routing.quota (4.28.0, ADR-043): daily spend quotas, shared by processes, every refusal recorded."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from relay.routing import QuotaLimits, SpendQuota

SRC = Path(__file__).resolve().parent.parent / "src"
T0 = 1_802_390_400.0  # 2027-02-12T00:00:00Z, a UTC midnight
LIMITS = QuotaLimits({"user": 1.00, "workspace": 5.00, "agent": 20.00, "feature": 30.00},
                     overrides={"user:7": 0.10})


def test_a_reservation_counts_against_every_principal(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    assert q.reserve(["user:1", "workspace:ws"], 0.40, T0, "a").allowed
    assert (q.spent("user:1", T0), q.spent("workspace:ws", T0)) == (0.4, 0.4)


def test_the_principal_that_would_pass_its_limit_refuses_and_nothing_is_counted(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    assert q.reserve(["user:1", "workspace:ws"], 0.60, T0 + 10, "a").allowed
    d = q.reserve(["user:1", "workspace:ws"], 0.60, T0 + 3600, "b")
    assert (d.allowed, d.refused_by, d.retry_after_s) == (False, "user:1", 82800)
    assert q.spent("workspace:ws", T0) == 0.6  # all or nothing
    assert q.refusals() == [("b", "user:1")]


def test_an_override_and_an_unknown_kind(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    assert not q.reserve(["user:7"], 0.20, T0, "a").allowed
    assert q.reserve(["robot:1"], 0.01, T0, "b").refused_by == "robot:1"  # no limit set: fail closed
    assert q.reserve(["user"], 0.01, T0, "c").refused_by == "user"


def test_the_same_ref_is_charged_once(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    assert q.reserve(["user:1"], 0.30, T0, "job:ws:k1").allowed
    again = q.reserve(["user:1"], 0.30, T0 + 5, "job:ws:k1")
    assert again.allowed and again.replayed and q.spent("user:1", T0) == 0.3


def test_settling_replaces_the_estimate_with_the_actual_cost(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    q.reserve(["agent:triage-worker"], 0.05, T0, "call:1")
    q.settle("call:1", 0.012, T0 + 4)
    q.settle("call:1", 0.012, T0 + 5)  # settling twice changes nothing
    assert q.spent("agent:triage-worker", T0) == 0.012
    with pytest.raises(KeyError):
        q.settle("never-reserved", 0.01, T0)


def test_a_new_utc_day_starts_from_zero(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    assert q.reserve(["user:1"], 1.00, T0 + 86399, "a").allowed
    assert not q.reserve(["user:1"], 0.01, T0 + 86399, "b").allowed
    assert q.reserve(["user:1"], 0.01, T0 + 86400, "c").allowed


def test_two_processes_cannot_both_spend_the_last_dollar(tmp_path):
    db = str(tmp_path / "q.db")
    SpendQuota(db, LIMITS).close()
    code = ("import sys; from relay.routing import QuotaLimits, SpendQuota; "
            "q = SpendQuota(sys.argv[1], QuotaLimits({'user': 1.0})); "
            "print(sum(q.reserve(['user:1'], 0.01, 1802390400.0, f'{sys.argv[2]}-{i}').allowed for i in range(80)))")
    env = dict(os.environ, PYTHONPATH=str(SRC))
    procs = [subprocess.Popen([sys.executable, "-c", code, db, tag], stdout=subprocess.PIPE, text=True, env=env)
             for tag in ("a", "b")]
    assert sum(int(p.communicate(timeout=120)[0]) for p in procs) == 100


def test_refusals_are_counted_by_kind_for_an_alert(tmp_path):
    q = SpendQuota(str(tmp_path / "q.db"), LIMITS)
    q.reserve(["user:7"], 0.20, T0 + 10, "a")              # refused by the user override
    q.reserve(["robot:1"], 0.01, T0 + 20, "b")             # refused: no limit for the kind
    q.reserve(["user:1"], 0.01, T0 + 30, "c")              # allowed
    q.reserve(["user:7"], 0.20, T0 + 4000, "d")            # outside the hour
    assert q.refusal_counts(T0, T0 + 3600) == {"robot": 1, "user": 1}
