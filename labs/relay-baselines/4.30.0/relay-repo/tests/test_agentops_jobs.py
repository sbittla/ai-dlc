"""The agent job queue (4.30.0, ADR-049): business-key deduplication, fenced leases, retries with jitter and
Retry-After, the dead-letter state, cancellation between steps, approval waits and person-only redrive."""

import pytest

from relay.agentops.jobs import (AgentJobQueue, JobCancelled, JobConflict, LeaseLost, backoff_s, jitter_fraction,
                                 retry_delay_s)

T = 1_800_000_000.0
PEOPLE = frozenset({"priya.n", "sam.o"})


def q():
    return AgentJobQueue()


def test_the_same_business_key_is_one_job_however_often_it_is_delivered():
    queue = q()
    first, created = queue.enqueue("refund", "ch_0042", {"charge": "ch_0042"}, T)
    again, created_again = queue.enqueue("refund", "ch_0042", {"charge": "ch_0042"}, T + 61)
    assert created and not created_again and again.id == first.id
    assert queue.counts()["queued"] == 1
    assert [e["event"] for e in queue.events(first.id)] == ["enqueued", "duplicate_enqueue"]


def test_the_same_key_with_a_different_payload_is_a_conflict_not_a_guess():
    queue = q()
    queue.enqueue("refund", "ch_0042", {"charge": "ch_0042", "amount": 180}, T)
    with pytest.raises(JobConflict):
        queue.enqueue("refund", "ch_0042", {"charge": "ch_0042", "amount": 360}, T)


def test_a_claim_takes_a_new_lease_token_and_the_old_holder_is_fenced_out():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T)
    a = queue.claim("w1", T, lease_s=60)
    b = queue.claim("w2", T + 61, lease_s=60)  # w1's lease expired while it was still working
    assert (a.lease_token, b.lease_token) == (1, 2) and b.attempts == 2
    with pytest.raises(LeaseLost):
        queue.heartbeat(job.id, a.lease_token, T + 62, 60)
    with pytest.raises(LeaseLost):
        queue.complete(job.id, a.lease_token, {"late": True}, T + 63)
    queue.complete(job.id, b.lease_token, {"ok": True}, T + 64)
    assert queue.get(job.id).status == "done" and queue.get(job.id).result == {"ok": True}


def test_heartbeat_extends_the_lease_so_a_slow_run_is_not_redelivered():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T)
    claimed = queue.claim("w1", T, lease_s=60)
    queue.heartbeat(job.id, claimed.lease_token, T + 50, 60)
    assert queue.claim("w2", T + 70, lease_s=60) is None


def test_retry_delay_is_full_jitter_and_never_shorter_than_retry_after():
    assert 0 <= jitter_fraction(7, 1) < 1
    assert [backoff_s(7, n) <= 15 * 2 ** (n - 1) for n in (1, 2, 3, 4)] == [True] * 4
    assert backoff_s(7, 2) != backoff_s(8, 2)  # two jobs that failed together do not retry together
    assert retry_delay_s(7, 1, retry_after_s=90) == 90
    assert retry_delay_s(7, 1, retry_after_s=0.5) == max(0.5, backoff_s(7, 1))


def test_a_retryable_failure_requeues_until_attempts_run_out_then_dead_letters():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T, max_attempts=2)
    c1 = queue.claim("w1", T, 60)
    assert queue.fail(job.id, c1.lease_token, "timeout", T + 1) == "queued"
    later = queue.get(job.id).available_at
    assert later >= T + 1
    c2 = queue.claim("w1", later, 60)
    assert queue.fail(job.id, c2.lease_token, "timeout", later + 1) == "dead"
    dead = queue.get(job.id)
    assert dead.dead_reason == "attempts_exhausted" and [j.id for j in queue.dead_letters()] == [job.id]


def test_a_poison_payload_goes_straight_to_the_dead_letter_state():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {}, T)
    c = queue.claim("w1", T, 60)
    assert queue.fail(job.id, c.lease_token, "task_id missing", T, retryable=False, dead_reason="poison_payload") \
        == "dead"
    assert queue.get(job.id).attempts == 1 and queue.get(job.id).dead_reason == "poison_payload"


def test_a_job_that_kills_its_worker_every_time_reaches_a_person():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T, max_attempts=2)
    queue.claim("w1", T, 60)
    queue.claim("w2", T + 61, 60)
    assert queue.claim("w3", T + 122, 60) is None
    assert queue.get(job.id).status == "dead" and queue.get(job.id).dead_reason == "lease_expired"


def test_cancelling_a_queued_job_is_immediate_and_a_running_one_stops_at_its_next_heartbeat():
    queue = q()
    queued, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T)
    running, _ = queue.enqueue("spec-to-pr", "RLY-2", {"task_id": "RLY-2"}, T)
    assert queue.cancel(queued.id, "priya.n", T) == "cancelled"
    c = queue.claim("w1", T, 60)
    assert c.id == running.id
    assert queue.cancel(running.id, "priya.n", T + 5) == "running"
    with pytest.raises(JobCancelled):
        queue.heartbeat(running.id, c.lease_token, T + 6, 60)
    assert queue.get(running.id).status == "cancelled"
    assert queue.cancel(running.id, "sam.o", T + 7) == "cancelled"


def test_waiting_for_an_approval_spends_no_attempt_and_waking_requeues():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T, max_attempts=1)
    c = queue.claim("w1", T, 60)
    queue.park(job.id, c.lease_token, "awaiting_approval", T + 1)
    assert queue.get(job.id).status == "waiting" and queue.get(job.id).attempts == 0
    assert queue.claim("w1", T + 2, 60) is None
    assert queue.wake(job.id, T + 3, "priya.n")
    assert queue.claim("w1", T + 3, 60).attempts == 1


def _authenticate(proof):
    """Stands in for ApprovalGate.authenticate: a proof from the person issuer naming a person."""
    if proof.get("iss") != "https://login.relay.example" or proof.get("sub") not in PEOPLE:
        raise ValueError("bad_person_proof")
    return proof["sub"]


def test_only_an_authenticated_person_with_a_reason_may_redrive_a_dead_job():
    queue = q()
    job, _ = queue.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T, max_attempts=1)
    c = queue.claim("w1", T, 60)
    queue.fail(job.id, c.lease_token, "timeout", T)
    sam = {"iss": "https://login.relay.example", "sub": "sam.o"}
    with pytest.raises(PermissionError):
        queue.redrive(job.id, {"iss": "https://token.actions.githubusercontent.com", "sub": "sam.o"},
                      "provider recovered at 10:20", T, _authenticate)
    with pytest.raises(PermissionError):
        queue.redrive(job.id, {"iss": "https://login.relay.example", "sub": "spec-to-pr-helper"},
                      "provider recovered at 10:20", T, _authenticate)
    with pytest.raises(ValueError):
        queue.redrive(job.id, sam, "retry", T, _authenticate)
    again = queue.redrive(job.id, sam, "provider recovered at 10:20 UTC", T + 5, _authenticate)
    assert again.status == "queued" and again.attempts == 0
    assert queue.events(job.id)[-1] == {"at": T + 5, "event": "redriven", "actor": "sam.o",
                                        "reason": "provider recovered at 10:20 UTC"}


def test_two_processes_share_the_queue_file(tmp_path):
    db = str(tmp_path / "relay.db")
    a, b = AgentJobQueue(db), AgentJobQueue(db)
    a.enqueue("spec-to-pr", "RLY-1", {"task_id": "RLY-1"}, T)
    first = b.claim("w2", T, 60)
    assert first is not None and a.claim("w1", T, 60) is None
