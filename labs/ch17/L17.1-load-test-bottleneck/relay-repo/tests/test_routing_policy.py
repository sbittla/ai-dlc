"""relay.routing.policy (4.28.0, ADR-042): routes, the policy, and the timeout check behind Chapter 17's incident."""

import pytest

from relay.routing import Route, RoutePolicy, route_problems

LARGE = Route("large", "sim-large", "triage-v3.1", max_output_tokens=64, timeout_s=10.0)
REASONER = Route("reasoner", "sim-reasoner", "triage-v3.1", max_output_tokens=1200, timeout_s=30.0)


def test_scores_at_or_above_the_threshold_take_the_hard_route():
    policy = RoutePolicy(LARGE, REASONER, threshold=1.5)
    assert [policy.choose(s).name for s in (1.49, 1.5, 3.0, None)] == ["large", "reasoner", "reasoner", "large"]


def test_invalid_output_falls_back_to_the_default_route_once():
    policy = RoutePolicy(LARGE, REASONER, threshold=1.5)
    assert policy.fallback(REASONER) == LARGE and policy.fallback(LARGE) is None


def test_a_hard_route_and_a_threshold_come_together():
    with pytest.raises(ValueError):
        RoutePolicy(LARGE, REASONER)
    with pytest.raises(ValueError):
        Route("bad", "sim-large", "triage-v3.1", max_output_tokens=0, timeout_s=10.0)


def test_the_incidents_route_could_run_past_its_timeout():
    # The reasoning model behind the worker's 10 s timeout with a 1,200-token limit, at an assumed 60 output
    # tokens per second and a 3 s p99 time to first token: 3 + 1200/60 = 23 s > 10 s.
    incident = Route("incident", "sim-reasoner", "triage-v3.1", max_output_tokens=1200, timeout_s=10.0)
    assert route_problems(incident, ttft_p99_s=3.0, output_tokens_per_s=60.0) == [
        "incident: a call allowed 1200 output tokens can take 23.0 s, past the 10 s timeout; "
        "lower the limit or raise the timeout"]
    assert route_problems(REASONER, ttft_p99_s=3.0, output_tokens_per_s=60.0) == []
