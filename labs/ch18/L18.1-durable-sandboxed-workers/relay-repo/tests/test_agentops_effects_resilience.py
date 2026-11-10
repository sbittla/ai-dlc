"""The effect ledger and the resilience primitives (4.30.0, ADR-049)."""

import pytest

from relay.agentops.effects import EffectConflict, EffectLedger, UnknownEffectOutcome
from relay.agentops.resilience import CircuitBreaker, parse_retry_after

T = 1_800_000_000.0


class Provider:
    """A payment provider that may or may not honour an idempotency key."""

    def __init__(self, dedupes: bool) -> None:
        self.dedupes, self.calls, self.refunds = dedupes, 0, {}

    def refund(self, key: str, args: dict) -> dict:
        self.calls += 1
        if self.dedupes and key in self.refunds:
            return self.refunds[key]
        refund = {"refund_id": f"re_{len(self.refunds) + self.calls}", "amount": args["amount"]}
        self.refunds.setdefault(key, refund)
        return refund


def test_two_runs_for_the_same_charge_refund_it_once():
    ledger, provider = EffectLedger(), Provider(dedupes=False)
    args = {"charge": "ch_0042", "amount": 180}
    first, replayed_1 = ledger.perform("refund:ch_0042", "refund", args, "run-a", provider.refund)
    second, replayed_2 = ledger.perform("refund:ch_0042", "refund", args, "run-b", provider.refund)
    assert (replayed_1, replayed_2) == (False, True) and first == second and provider.calls == 1
    assert ledger.get("refund:ch_0042")["first_run"] == "run-a" and ledger.counts() == {"started": 0, "ok": 1,
                                                                                      "replays": 1}


def test_the_same_key_with_different_arguments_is_refused():
    ledger, provider = EffectLedger(), Provider(dedupes=False)
    ledger.perform("refund:ch_0042", "refund", {"charge": "ch_0042", "amount": 180}, "run-a", provider.refund)
    with pytest.raises(EffectConflict):
        ledger.perform("refund:ch_0042", "refund", {"charge": "ch_0042", "amount": 360}, "run-b", provider.refund)


def _crash(key, args):
    raise RuntimeError("process died after the provider call, before the ledger recorded it")


def test_a_started_effect_is_never_repeated_blindly():
    ledger, provider = EffectLedger(), Provider(dedupes=False)
    args = {"charge": "ch_0042", "amount": 180}
    with pytest.raises(RuntimeError):
        ledger.perform("refund:ch_0042", "refund", args, "run-a", _crash)
    with pytest.raises(UnknownEffectOutcome):
        ledger.perform("refund:ch_0042", "refund", args, "run-a", provider.refund)
    assert provider.calls == 0


def test_a_provider_that_honours_the_key_lets_a_started_effect_be_repeated_safely():
    ledger, provider = EffectLedger(), Provider(dedupes=True)
    args = {"charge": "ch_0042", "amount": 180}
    provider.refund("refund:ch_0042", args)  # the call that happened before the crash
    with pytest.raises(RuntimeError):
        ledger.perform("refund:ch_0042", "refund", args, "run-a", _crash)
    result, replayed = ledger.perform("refund:ch_0042", "refund", args, "run-a", provider.refund,
                                      provider_idempotent=True)
    assert not replayed and len(provider.refunds) == 1 and result == provider.refunds["refund:ch_0042"]


def test_a_started_effect_past_the_providers_key_window_is_not_repeated():
    now = [T]
    ledger, provider = EffectLedger(clock=lambda: now[0]), Provider(dedupes=True)
    args = {"charge": "ch_0042", "amount": 180}
    with pytest.raises(RuntimeError):
        ledger.perform("refund:ch_0042", "refund", args, "run-a", _crash)
    now[0] += 3 * 86_400  # redriven three days later: the provider has forgotten the key
    with pytest.raises(UnknownEffectOutcome):
        ledger.perform("refund:ch_0042", "refund", args, "run-a", provider.refund, provider_idempotent=True,
                       provider_window_s=86_400)
    assert provider.calls == 0


def test_the_ledger_is_shared_between_processes(tmp_path):
    db = str(tmp_path / "relay.db")
    provider = Provider(dedupes=False)
    EffectLedger(db).perform("pr:RLY-1", "pull_request", {"task": "RLY-1"}, "run-a", lambda k, a: {"number": 5100})
    result, replayed = EffectLedger(db).perform("pr:RLY-1", "pull_request", {"task": "RLY-1"}, "run-b",
                                                provider.refund)
    assert replayed and result == {"number": 5100} and provider.calls == 0


class Clock:
    def __init__(self) -> None:
        self.t = T

    def __call__(self) -> float:
        return self.t


def test_the_breaker_opens_after_the_threshold_and_lets_one_probe_through_after_the_cooldown():
    clock = Clock()
    breaker = CircuitBreaker("model", clock, threshold=3, window_s=60, cooldown_s=60)
    for _ in range(3):
        assert breaker.allow()
        breaker.record_failure()
    assert breaker.state == "open" and not breaker.allow()
    clock.t += 61
    assert breaker.allow() and breaker.state == "half_open"
    assert not breaker.allow()  # one probe at a time
    breaker.record_success()
    assert breaker.state == "closed" and [s for _, s in breaker.transitions] == ["open", "half_open", "closed"]


def test_a_failed_probe_reopens_and_retry_after_lengthens_the_cooldown():
    clock = Clock()
    breaker = CircuitBreaker("model", clock, threshold=1, cooldown_s=30)
    breaker.record_failure(retry_after_s=120)
    assert breaker.open_until == T + 120
    clock.t += 121
    assert breaker.allow()
    breaker.record_failure()
    assert breaker.state == "open" and breaker.open_until == clock.t + 30


def test_failures_outside_the_window_do_not_add_up():
    clock = Clock()
    breaker = CircuitBreaker("model", clock, threshold=2, window_s=60)
    breaker.record_failure()
    clock.t += 61
    breaker.record_failure()
    assert breaker.state == "closed"


@pytest.mark.parametrize("value, expected", [
    ("30", 30.0), (" 0 ", 0.0), (None, None), ("", None), ("-5", None), ("soon", None), ("²", None), ("99999", 3600.0),
    ("Thu, 01 Jan 2027 00:01:00 GMT", 60.0),
])
def test_retry_after_is_seconds_or_an_http_date_capped_at_an_hour(value, expected):
    now = 1798761600.0  # 2027-01-01T00:00:00Z
    assert parse_retry_after(value, now) == expected


# MUST FIX 4 (round 1): a half-open trial that ends without a success or a failure must not wedge the breaker.
def _wedge_setup(trial_mode):
    from relay.agentops import AgentJobQueue, LeaseLost, PoisonPayload, RateLimited
    from relay.agentops.jobs import JobCancelled
    from relay.agentops.worker import AgentKind, AgentWorker, Outcome

    clock = Clock()
    queue = AgentJobQueue()
    breaker = CircuitBreaker("model", clock, threshold=3, window_s=120, cooldown_s=60)

    def handler(ctx):
        mode = ctx.job.payload["mode"]
        if mode == "429":
            raise RateLimited("model", 30)
        if mode == "poison":
            raise PoisonPayload("task missing")
        if mode == "cancel":
            raise JobCancelled(str(ctx.job.id))
        if mode == "lost":
            raise LeaseLost(str(ctx.job.id))
        if mode == "bug":
            raise KeyError("unexpected")
        return Outcome("finished", "ok")
    worker = AgentWorker(queue, {"k": AgentKind("model", handler)}, "w1", clock, {"model": breaker})
    for i in range(3):
        queue.enqueue("k", f"rl{i}", {"mode": "429"}, clock())
    assert [worker.run_once() for _ in range(3)] == ["retry", "retry", "retry"] and breaker.state == "open"
    for i in range(3):
        queue.conn.execute("UPDATE agent_jobs SET available_at = 1e12 WHERE dedup_key = ?", (f"rl{i}",))
    queue.enqueue("k", "trial", {"mode": trial_mode}, clock())
    queue.enqueue("k", "good", {"mode": "ok"}, clock())
    clock.t += 61
    return clock, queue, breaker, worker


@pytest.mark.parametrize("mode, outcome, state", [("poison", "dead", "half_open"), ("cancel", "cancelled", "half_open"),
                                                  ("lost", "lost_lease", "half_open"), ("bug", "retry", "open")])
def test_a_trial_that_ends_without_a_verdict_releases_the_breaker(mode, outcome, state):
    clock, queue, breaker, worker = _wedge_setup(mode)
    assert worker.run_once() == outcome
    assert breaker.state == state and breaker.probing is False
    for _ in range(10):  # the healthy job behind the trial is served; nothing waits for a restart
        clock.t += 61
        worker.run_once()
    assert queue.get(5).status == "done"
