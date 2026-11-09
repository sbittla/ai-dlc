"""The agent loop and its stopping conditions (4.24.0, ADR-024). Each policy is a script, so every case
can be followed by hand."""

from agents_helpers import PR_ARGS, World
from relay.agents import Budget, Decision, StepRecord, StopRules, run_loop, stop_reason
from relay.agents.budget import Meter


class Script:
    """A policy that plays back a fixed list of decisions; each model call costs 10,000 input tokens."""

    actor = "spec-to-pr-helper"

    def __init__(self, steps):
        self.steps = list(steps)
        self.seen = []

    def next_call(self):
        return "sim-large", 10_000, 500, 0  # estimate: $0.04 input + $0.01 for a 500-token allowance

    def decide(self):
        action, tool, args, note = self.steps.pop(0) if self.steps else ("tool", "run_tests", {"target": "approved"},
                                                                          "")
        return Decision(action, "sim-large", 10_000, 200, 2.0, tool=tool, args=args, note=note)

    def observe(self, tool, result):
        self.seen.append(tool)


def meter(**kw):
    return Meter(Budget(**{"max_steps": 100, "max_usd": 10, "max_seconds": 1000, **kw}))


def test_stop_reason_by_hand():
    rules = StopRules(repeat_limit=3, no_progress_limit=4)
    m = meter()
    assert stop_reason(m, [], rules) is None
    two = [StepRecord("run_tests", True, "tests:a", "p1"), StepRecord("run_tests", True, "tests:a", "p2")]
    assert stop_reason(m, two, rules) is None
    three = two + [StepRecord("run_tests", True, "tests:a", "p3")]
    assert stop_reason(m, three, rules) == "repeated_failure:tests:a"


def test_the_first_signature_to_reach_the_limit_is_reported():
    h = [StepRecord("t", True, s, str(i)) for i, s in enumerate(["b", "a", "b", "a", "b", "a"])]
    assert stop_reason(meter(), h, StopRules(repeat_limit=3)) == "repeated_failure:b"


def test_no_progress_means_no_new_state_in_the_last_n_steps():
    rules = StopRules(repeat_limit=9, no_progress_limit=3)
    h = [StepRecord("read_file", True, None, "read:a"), StepRecord("read_file", True, None, "read:b"),
         StepRecord("read_file", True, None, "read:a"), StepRecord("read_file", True, None, None),
         StepRecord("read_file", True, None, "read:b")]
    assert stop_reason(meter(), h, rules) == "no_progress"
    assert stop_reason(meter(), h[:4], rules) is None  # read:b (step 2) is still within the last three


def test_budget_comes_first():
    m = meter(max_steps=1)
    m.charge_tool("a", 0)
    h = [StepRecord("t", True, "x", None)] * 3
    assert stop_reason(m, h, StopRules()) == "budget:steps"


def test_a_failing_loop_stops_after_three_identical_failures():
    w = World()
    result = run_loop(Script([]), w.boundary, StopRules(repeat_limit=3), done_check=lambda: False)
    assert (result.status, result.reason) == ("handed_back", "repeated_failure:tests:test_a")
    assert w.meter.model_calls == 3 and w.meter.steps == 6


def test_finish_is_accepted_only_if_the_done_check_agrees():
    w = World()
    script = Script([("finish", None, {}, "all green"), ("finish", None, {}, "really")])
    done = iter([False, True])
    result = run_loop(script, w.boundary, StopRules(), done_check=lambda: next(done))
    assert (result.status, result.reason) == ("finished", "really")
    assert result.history == [StepRecord("finish", False, "not_done")]


def test_the_money_limit_stops_the_loop_before_a_call_that_would_cross_it():
    w = World(budget=Budget(max_steps=100, max_usd=0.12, max_seconds=1000))
    result = run_loop(Script([("tool", "read_file", {"path": "src/relay/x.py"}, "")] * 10), w.boundary,
                      StopRules(no_progress_limit=50), done_check=lambda: False)
    assert (result.status, result.reason) == ("stopped", "budget:usd")
    assert w.meter.usd <= 0.12  # three calls of $0.044 would cross it, so the third never starts
    assert w.meter.model_calls == 2


def test_the_loop_estimates_the_call_itself_and_counts_overruns():
    w = World(budget=Budget(max_steps=100, max_usd=10, max_seconds=1000))

    class Liar(Script):
        def next_call(self):
            return "sim-large", 10, 1, 0  # claims a tiny call
    run_loop(Liar([("hand_back", None, {}, "done")]), w.boundary, StopRules(), done_check=lambda: False)
    assert w.meter.overruns == 1  # the call sent 10,000 tokens and wrote 200


def test_a_gated_call_pauses_the_run_with_the_approval_id():
    w = World()
    result = run_loop(Script([("tool", "open_pull_request", PR_ARGS, "")]), w.boundary, StopRules(),
                      done_check=lambda: False)
    assert result.status == "awaiting_approval" and result.approval_id.startswith("apv-")


def test_a_tripped_kill_switch_ends_the_run_as_revoked():
    from relay.audit import trip
    w = World()
    script = Script([("tool", "read_file", {"path": "src/relay/x.py"}, "")] * 3)
    original = script.observe

    def observe(tool, result):
        original(tool, result)
        trip(w.registry, w.trail, "spec-to-pr-helper", actor="detection:DR-002", reason="drill")
    script.observe = observe
    result = run_loop(script, w.boundary, StopRules(), done_check=lambda: False)
    assert (result.status, result.reason) == ("revoked", "disabled")
    assert len(result.history) == 1


def test_hand_back_carries_the_agent_reason_and_history_survives_a_resume():
    w = World()
    first = run_loop(Script([("tool", "run_tests", {"target": "approved"}, "")] * 2 + [("hand_back", None, {},
                                                                                         "need a person")]),
                     w.boundary, StopRules(), done_check=lambda: False)
    assert (first.status, first.reason) == ("handed_back", "agent:need a person")
    resumed = run_loop(Script([]), w.boundary, StopRules(repeat_limit=3), done_check=lambda: False,
                       history=first.history)
    assert resumed.reason == "repeated_failure:tests:test_a" and len(resumed.history) == 3
