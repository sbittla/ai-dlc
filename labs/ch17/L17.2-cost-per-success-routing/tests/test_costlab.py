"""Hand-checkable tests for TODOs 1-5. Each expected value is worked out in the comment beside it."""

import pytest

import costlab.abuse as abuse
import costlab.production as production
from costlab.agentcost import costs
from costlab.caching import CacheResult, prefix_cost, simulate
from costlab.compare import summarize
from costlab.production import Call, Outcome, triage

TICKET = {"id": "T1", "text": "x", "difficulty": "hard",
          "expected": {"category": "bug", "priority": "P1", "team": "platform"}}
GOOD = '{"category": "bug", "priority": "P1", "team": "platform"}'
WRONG = '{"category": "bug", "priority": "P2", "team": "platform"}'
ROUTE = {"model": "sim-reasoner", "max_output_tokens": 1000, "timeout_s": 10.0}


def script(monkeypatch, calls):
    """Make production.call return the given (latency, text, stop) in order, each costing $0.01."""
    seq = iter(calls)

    def fake(model, ticket, run, attempt, max_out):
        lat, text, stop = next(seq)
        return Call(model, 100, 50, 0, lat, lat, text, stop, 0.01)

    monkeypatch.setattr(production, "call", fake)


# ---------------------------------------------------------------- TODO 1

def test_a_good_first_call(monkeypatch):
    script(monkeypatch, [(3.0, GOOD, "end_turn")])
    o = triage(TICKET, 1, ROUTE)
    assert (o.result, o.calls, o.timeouts, o.usd, o.seconds, o.first_call_correct) == ("correct", 1, 0, 0.01, 3.0, True)


def test_two_timeouts_then_an_answer(monkeypatch):
    # 10 (timeout) + 10 backoff + 10 (timeout) + 20 backoff + 4 = 54 s; three calls billed.
    script(monkeypatch, [(12.0, GOOD, "end_turn"), (15.0, GOOD, "end_turn"), (4.0, WRONG, "end_turn")])
    o = triage(TICKET, 1, ROUTE)
    assert (o.result, o.calls, o.timeouts, o.usd, o.seconds) == ("wrong", 3, 2, pytest.approx(0.03), 54.0)
    assert o.first_call_correct  # the gate, with no clock, would have scored the first call correct


def test_three_timeouts_go_to_a_person(monkeypatch):
    # 10 + 10 + 10 + 20 + 10 = 60 s, nothing after the last attempt.
    script(monkeypatch, [(11.0, GOOD, "end_turn")] * 3)
    o = triage(TICKET, 1, ROUTE)
    assert (o.result, o.timeouts, o.seconds) == ("needs_human", 3, 60.0)


def test_unusable_output_is_retried_once(monkeypatch):
    # prose (unusable) 2 s + 10 s backoff, then truncated 3 s: a second unusable answer goes to a person. 15 s.
    script(monkeypatch, [(2.0, "Sure! " + GOOD, "end_turn"), (3.0, "", "max_tokens")])
    o = triage(TICKET, 1, ROUTE)
    assert (o.result, o.calls, o.seconds) == ("needs_human", 2, 15.0)


# ---------------------------------------------------------------- TODO 2

def outcome(result, calls, usd, seconds, lats, route="default", first=True):
    return Outcome("T", 1, route, result, calls, 0, usd, seconds, first, usd, tuple(lats), tuple(lats))


def test_summary_counts_cost_per_correct_and_latency():
    outs = (outcome("correct", 1, 0.01, 2.0, [2.0]), outcome("wrong", 1, 0.01, 4.0, [4.0], route="hard"),
            outcome("needs_human", 3, 0.03, 60.0, [11.0, 11.0, 11.0], first=False),
            outcome("correct", 1, 0.01, 6.0, [6.0]))
    s = summarize("x", outs)
    assert (s.correct, s.wrong, s.needs_human, s.quality) == (2, 1, 1, 0.5)
    assert s.usd_per_correct == pytest.approx(0.06 / 2) and s.usd_per_call == pytest.approx(0.06 / 6)
    assert (s.call_p95_s, s.suggestion_p50_s, s.suggestion_p95_s) == (11.0, 4.0, 6.0)   # 6 call latencies; 3 waits
    assert s.wrong_share_of_suggestions == pytest.approx(1 / 3) and s.hard_route_share == 0.25


# ---------------------------------------------------------------- TODO 3

def test_cache_writes_and_reads_by_hand():
    # 0 write; 100 read; 450 write (350 s after 100); 700 read (250 s after 450); 1300 write.
    assert simulate([0, 100, 450, 700, 1300], 1000) == CacheResult(5, 3, 2, 0)
    assert simulate([0, 100], 400) == CacheResult(2, 0, 0, 2)  # under the 512-token minimum


def test_prefix_cost_by_hand():
    # 1,000 tokens, sim-large: without 5 x $0.004 = $0.02; with 3 writes x $0.005 + 2 reads x $0.0002 = $0.0154.
    without, with_cache = prefix_cost(CacheResult(5, 3, 2, 0), 1000)
    assert without == pytest.approx(0.02) and with_cache == pytest.approx(0.0154)


# ---------------------------------------------------------------- TODO 4

def test_the_user_limit_stops_a_token_after_its_share(monkeypatch):
    tiny = dict(abuse.ABUSE, minutes=2, limits={"user": 0.10, "workspace": 10.0},
                scenarios={"t": {"attacker_tokens": 1, "per_token_per_minute": 10}},
                legitimate={"users": 1, "per_minute": 0.0})
    monkeypatch.setattr(abuse, "ABUSE", tiny)
    monkeypatch.setattr(abuse, "ceiling_usd", lambda *a: 0.03)
    r = abuse.burst("t")
    # 0.03 x 3 = 0.09 <= 0.10; a fourth would make 0.12. 20 sent, 3 accepted, 17 refusals recorded.
    assert (r.attacker_sent, r.attacker_accepted, r.refusals_recorded, r.reserved_usd) == (20, 3, 17, 0.09)
    assert abuse.burst("t", quotas=False).attacker_accepted == 20


# ---------------------------------------------------------------- TODO 5

def test_agent_run_costs_by_hand():
    run = {"input_tokens": 100_000, "cached_tokens": 80_000, "output_tokens": 1_000}
    # Lab 10.1: 20,000 x 4 + 80,000 x 0.2 + 1,000 x 20 = 80,000 + 16,000 + 20,000 = $0.116
    # surcharge: 20,000 x 4 x 0.25 = 20,000 -> $0.136; no caching: 100,000 x 4 + 20,000 = $0.42
    assert costs(run) == pytest.approx((0.116, 0.136, 0.42))
    assert costs({"input_tokens": 1000, "cached_tokens": 0, "output_tokens": 0})[1] == pytest.approx(0.004)
