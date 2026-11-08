"""The durable triage queue: idempotency keys, leases, retries and the human queue (ADR-007)."""

import pytest

from relay.worker import IdempotencyConflict, TriageQueue
from relay.worker.queue import backoff_s

T0 = 1_794_000_000.0  # 2026-11-08 in Unix seconds, roughly; only differences matter


@pytest.fixture
def q():
    return TriageQueue(":memory:")


def test_enqueue_creates_a_queued_job(q):
    job, created = q.enqueue("ws-1", "key-00000001", "The board shows a 500 error", T0)
    assert created and job.status == "queued" and job.attempts == 0


def test_same_key_same_body_is_a_replay_not_a_second_job(q):
    first, _ = q.enqueue("ws-1", "key-00000001", "text", T0)
    again, created = q.enqueue("ws-1", "key-00000001", "text", T0 + 5)
    assert not created and again.id == first.id
    assert q.counts()["queued"] == 1


def test_same_key_different_body_is_a_conflict(q):
    q.enqueue("ws-1", "key-00000001", "text", T0)
    with pytest.raises(IdempotencyConflict):
        q.enqueue("ws-1", "key-00000001", "other text", T0)


def test_keys_are_scoped_to_a_workspace(q):
    a, _ = q.enqueue("ws-1", "key-00000001", "text", T0)
    b, created = q.enqueue("ws-2", "key-00000001", "text", T0)
    assert created and a.id != b.id


def test_claim_takes_oldest_and_sets_a_lease(q):
    a, _ = q.enqueue("ws-1", "key-0000000a", "first", T0)
    q.enqueue("ws-1", "key-0000000b", "second", T0)
    job = q.claim("w1", T0, lease_s=60)
    assert job.id == a.id and job.status == "running" and job.attempts == 1
    assert job.lease_owner == "w1" and job.lease_until == T0 + 60


def test_a_leased_job_is_not_claimed_twice(q):
    q.enqueue("ws-1", "key-0000000a", "only", T0)
    assert q.claim("w1", T0, 60) is not None
    assert q.claim("w2", T0 + 59, 60) is None


def test_an_expired_lease_is_reclaimed_and_the_old_worker_is_fenced_out(q):
    q.enqueue("ws-1", "key-0000000a", "only", T0)
    job = q.claim("w1", T0, 60)
    again = q.claim("w2", T0 + 61, 60)           # w1 died, or is very slow
    assert again.id == job.id and again.attempts == 2 and again.lease_owner == "w2"
    assert q.complete(job.id, "w1", {"suggestion": {}}, T0 + 62) is False   # w1 wakes up: refused
    assert q.complete(job.id, "w2", {"suggestion": {}}, T0 + 62) is True
    assert q.get(job.id).status == "done"


def test_retry_backoff_then_needs_human(q):
    q.enqueue("ws-1", "key-0000000a", "only", T0)
    now = T0
    statuses = []
    for _ in range(3):
        job = q.claim("w1", now, 60)
        assert job is not None
        statuses.append(q.fail(job.id, "w1", "unavailable", now))
        now += backoff_s(job.attempts)
    assert statuses == ["queued", "queued", "needs_human"]
    assert q.counts()["needs_human"] == 1


def test_a_job_is_not_available_before_its_backoff(q):
    q.enqueue("ws-1", "key-0000000a", "only", T0)
    job = q.claim("w1", T0, 60)
    q.fail(job.id, "w1", "timeout", T0)
    assert q.claim("w1", T0 + 9, 60) is None
    assert q.claim("w1", T0 + 10, 60) is not None


def test_backoff_doubles_and_is_capped():
    assert [backoff_s(n) for n in (1, 2, 3, 4, 10)] == [10, 20, 40, 80, 300]


def test_non_retryable_failure_goes_straight_to_a_person(q):
    q.enqueue("ws-1", "key-0000000a", "only", T0)
    job = q.claim("w1", T0, 60)
    assert q.fail(job.id, "w1", "schema", T0, retryable=False) == "needs_human"


def test_queue_survives_a_restart(tmp_path):
    db = str(tmp_path / "relay.db")
    TriageQueue(db).enqueue("ws-1", "key-0000000a", "durable", T0)
    reopened = TriageQueue(db)
    assert reopened.counts()["queued"] == 1
    assert reopened.claim("w1", T0, 60).ticket_text == "durable"
