"""The tool-call boundary (4.24.0, ADR-025): every check, in order, with an audit record for each call."""

import pytest

from agents_helpers import PR_ARGS, World
from relay.agents import AgentRevoked, AwaitingApproval, Budget, BudgetExceeded
from relay.audit import trip, verify


def approve_pr(w, args=PR_ARGS):
    with pytest.raises(AwaitingApproval) as exc:
        w.boundary.call("open_pull_request", args)
    w.gate.decide(exc.value.approval_id, w.person("priya.n"), True, "diff read")


def test_a_valid_read_runs_and_is_audited_by_hash_with_owner_and_credential():
    w = World()
    r = w.boundary.call("read_file", {"path": "src/relay/x.py"})
    assert r.ok and r.value == "old\n"
    rec = w.trail.records[-1]
    assert (rec["action"], rec["outcome"], rec["agent_id"], rec["owner"], rec["on_behalf_of"], rec["credential"]) == (
        "tool.read_file", "ok", "spec-to-pr-helper", "sam.o", "priya.n", "jti-1")
    assert "path" not in rec["detail"] and len(rec["detail"]["args_sha256"]) == 64


@pytest.mark.parametrize("tool, args, code", [
    ("run_shell", {"cmd": "rm -rf /"}, "unknown_tool"),
    ("edit_file", {"path": "src/relay/roles.py", "content": "x"}, "path_not_allowed"),
    ("edit_file", {"path": "tests/test_x.py", "content": "x"}, "path_not_allowed"),
    ("read_file", {"path": "governance/agents.json"}, "path_not_allowed"),
    ("run_tests", {"target": "all"}, "invalid_args"),
])
def test_refusals_are_recorded_and_change_nothing(tool, args, code):
    w = World()
    r = w.boundary.call(tool, args)
    assert (r.ok, r.code, r.failure) == (False, code, f"refused:{code}")
    assert w.files == {"src/relay/x.py": "old\n"}
    assert w.trail.records[-1]["outcome"] == "refused" and w.trail.records[-1]["detail"]["code"] == code
    assert w.store.steps(w.run_id)[-1]["outcome"] == "refused"


def test_a_scope_the_token_does_not_hold_is_refused():
    from relay.agents import Param, ToolContract
    contracts = {"export": ToolContract("export", "d", (Param("q", "str"),), "read", scope="tasks:export:support")}
    w = World(contracts=contracts)
    w.boundary.handlers["export"] = lambda a: None
    assert w.boundary.call("export", {"q": "x"}).code == "scope_missing"


def test_the_kill_switch_stops_the_next_call_and_that_refusal_is_recorded():
    w = World()
    assert w.boundary.call("read_file", {"path": "src/relay/x.py"}).ok
    result = trip(w.registry, w.trail, "spec-to-pr-helper", actor="aisha.r", reason="drill")
    assert any("relay-spec-to-pr installation tokens" in s for s in result.external_steps)
    with pytest.raises(AgentRevoked) as exc:
        w.boundary.call("read_file", {"path": "src/relay/x.py"})
    assert exc.value.code == "disabled"
    last = w.trail.records[-1]
    assert (last["action"], last["outcome"]) == ("tool.read_file", "refused")
    assert last["detail"]["code"] == "revoked:disabled"
    assert verify(w.trail.records).ok


def test_a_refresh_without_a_fresh_person_proof_ends_as_delegation_expired_not_revoked():
    from relay.agents import DelegationExpired
    w = World()
    first = w.person("priya.n")
    w.session._subject = lambda: first  # the proof that came with the trigger, never renewed
    w.boundary.call("read_file", {"path": "src/relay/x.py"})
    w.clock.t += 850
    with pytest.raises(DelegationExpired) as exc:
        w.boundary.call("read_file", {"path": "src/relay/x.py"})
    assert (exc.value.status, exc.value.code) == ("delegation_expired", "bad_subject_token")
    assert w.trail.records[-1]["detail"]["code"] == "delegation_expired:bad_subject_token"
    assert w.registry.get("spec-to-pr-helper").enabled  # nothing was revoked


def test_tokens_last_15_minutes_and_are_refreshed_by_exchange():
    w = World()
    w.boundary.call("read_file", {"path": "src/relay/x.py"})
    w.clock.t += 850  # within 60 seconds of expiry: the session exchanges a new proof first
    w.boundary.call("read_file", {"path": "src/relay/x.py"})
    assert w.session.exchanges == 2


def test_the_budget_is_checked_before_any_effect_and_the_refusal_is_recorded():
    w = World(budget=Budget(max_steps=1, max_usd=1, max_seconds=100))
    assert w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "new\n"}).ok
    with pytest.raises(BudgetExceeded):
        w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "newer\n"})
    assert w.files["src/relay/x.py"] == "new\n"
    assert w.trail.records[-1]["detail"]["code"] == "budget:steps"


def test_a_pull_request_waits_for_approval_of_the_real_diff():
    w = World()
    approve_pr(w)
    assert w.prs == []
    assert w.boundary.call("open_pull_request", PR_ARGS).value == {"number": 100, "existing": False}
    assert w.prs[0]["diff"] == w.diff_sha()


def test_a_steered_agent_cannot_reuse_an_approval_after_changing_the_diff():
    w = World()
    approve_pr(w)
    old = w.diff_sha()
    w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "MALICIOUS\n"})
    with pytest.raises(AwaitingApproval):  # the agent sends the old hash; the boundary computes the real one
        w.boundary.call("open_pull_request", dict(PR_ARGS, diff_sha256=old))
    assert w.prs == []
    request = [r for r in w.trail.records if r["action"] == "approval.request"][-1]
    assert request["detail"]["bound"]["diff_sha256"] == w.diff_sha() != old


def test_a_denied_approval_is_a_refusal():
    w = World()
    with pytest.raises(AwaitingApproval) as exc:
        w.boundary.call("open_pull_request", PR_ARGS)
    w.gate.decide(exc.value.approval_id, w.person("priya.n"), False, "not yet")
    assert w.boundary.call("open_pull_request", PR_ARGS).code == "approval_denied"
    assert w.prs == []


def test_a_repeated_external_call_is_replayed_from_the_journal_not_repeated():
    w = World()
    approve_pr(w)
    first = w.boundary.call("open_pull_request", PR_ARGS)
    again = w.boundary.call("open_pull_request", PR_ARGS)
    assert again.replayed and again.value == first.value and len(w.prs) == 1
    assert w.trail.records[-1]["outcome"] == "replayed"


def test_editing_a_file_to_a_then_b_then_a_is_three_edits():
    w = World()
    for content in ("A\n", "B\n", "A\n"):
        assert not w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": content}).replayed
    assert w.files["src/relay/x.py"] == "A\n"
    assert [s["outcome"] for s in w.store.steps(w.run_id)] == ["ok", "ok", "ok"]


def test_an_interrupted_non_idempotent_step_is_not_run_again():
    w = World()
    from agents_helpers import sha
    from relay.agents import HELPER_TOOLS, args_sha256, idempotency_key
    args = {"path": "src/relay/x.py", "content": "new\n", "before_sha256": sha("old\n")}
    key = idempotency_key(w.run_id, HELPER_TOOLS["edit_file"], args)
    w.store.begin_step(w.run_id, key, "spec-to-pr-helper", "edit_file", args_sha256(args), "t")  # crash here
    r = w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "new\n"})
    assert (r.ok, r.code) == (False, "unknown_outcome")
    assert w.files["src/relay/x.py"] == "old\n"


def test_a_transient_error_on_an_idempotent_tool_is_retried():
    w = World()
    approve_pr(w)
    calls = []

    def flaky(args):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("502 Bad Gateway")
        return w.open_pr(args)
    w.boundary.handlers["open_pull_request"] = flaky
    assert w.boundary.call("open_pull_request", PR_ARGS).code == "ConnectionError"
    assert w.boundary.call("open_pull_request", PR_ARGS).ok and len(w.prs) == 1 and len(calls) == 2


def test_an_error_on_a_non_idempotent_tool_is_final_for_its_key():
    w = World()
    w.boundary.handlers["edit_file"] = lambda a: 1 / 0
    first = w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "z\n"})
    again = w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "z\n"})
    assert first.code == "ZeroDivisionError" and again.replayed and again.code == "ZeroDivisionError"


def test_search_results_never_include_paths_no_agent_may_read():
    w = World()
    w.search_hits = ["src/relay/y.py", ".env", "governance/agents.json", "infra/detection/rules.json"]
    r = w.boundary.call("search_code", {"pattern": "token"})
    assert r.value == ["src/relay/y.py"] and w.trail.records[-1]["detail"]["removed_paths"] == 3


def test_a_tool_that_raises_is_an_error_outcome_not_a_crash():
    w = World()
    w.boundary.handlers["run_prcheck"] = lambda a: 1 / 0
    r = w.boundary.call("run_prcheck", {})
    assert (r.ok, r.code, r.failure) == (False, "ZeroDivisionError", "error:run_prcheck")


def test_long_results_are_cut_to_the_contract_size():
    w = World()
    w.files["src/relay/x.py"] = "x" * 20000
    r = w.boundary.call("read_file", {"path": "src/relay/x.py"})
    assert r.truncated and len(r.value) == 12000


def test_a_contract_with_derived_arguments_and_no_provider_is_refused():
    w = World()
    del w.boundary.derive["edit_file"]
    assert w.boundary.call("edit_file", {"path": "src/relay/x.py", "content": "q\n"}).code == "underivable"


def test_the_trail_of_a_run_verifies():
    w = World()
    w.boundary.call("read_file", {"path": "src/relay/x.py"})
    w.boundary.call("run_shell", {})
    assert verify(w.trail.records).ok
