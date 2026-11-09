"""Durable run state, idempotent steps and resuming (4.24.0, ADR-026)."""

import pytest

from relay.agents import RunStore


def store_with_run():
    s = RunStore()
    run_id, created = s.start_run("req-7", "T-007", "workflow", "spec-to-pr-helper", "priya.n", "t0")
    assert created
    return s, run_id


def test_a_repeated_request_maps_to_the_same_run():
    s, run_id = store_with_run()
    again, created = s.start_run("req-7", "T-007", "workflow", "spec-to-pr-helper", "priya.n", "t1")
    assert (again, created) == (run_id, False)
    assert s.conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 1


def test_a_step_with_a_known_key_is_returned_not_repeated():
    s, run_id = store_with_run()
    seq, existing = s.begin_step(run_id, "key-1", "helper", "open_pull_request", "sha", "t1")
    assert (seq, existing) == (1, None)
    s.finish_step(run_id, seq, "ok", {"value": {"number": 101}})
    seq2, existing = s.begin_step(run_id, "key-1", "helper", "open_pull_request", "sha", "t2")
    assert seq2 == 1 and existing["outcome"] == "ok" and existing["result"] == {"value": {"number": 101}}
    assert len(s.steps(run_id)) == 1


def test_reads_have_no_key_and_are_always_new_steps():
    s, run_id = store_with_run()
    assert s.begin_step(run_id, None, "helper", "read_file", "sha", "t1")[0] == 1
    assert s.begin_step(run_id, None, "helper", "read_file", "sha", "t2")[0] == 2


def test_a_step_interrupted_before_its_outcome_is_found_on_resume():
    s, run_id = store_with_run()
    s.begin_step(run_id, "key-2", "helper", "open_pull_request", "sha", "t1")  # then the process dies
    assert [st["seq"] for st in s.unfinished_steps(run_id)] == [1]
    _, existing = s.begin_step(run_id, "key-2", "helper", "open_pull_request", "sha", "t2")
    assert existing["outcome"] == "started"


def test_checkpoints_and_status_are_durable(tmp_path):
    path = tmp_path / "runs.db"
    s = RunStore(path)
    run_id, _ = s.start_run("req-8", "T-008", "agent", "spec-to-pr-helper", "sam.o", "t0")
    s.save_checkpoint(run_id, {"meter": {"usd": 0.42}, "history": [["run_tests", False]]}, "t1")
    s.set_status(run_id, "awaiting_approval", "open_pull_request", "t2")
    s.close()
    again = RunStore(path)
    run = again.run(run_id)
    assert run["status"] == "awaiting_approval" and run["checkpoint"]["meter"] == {"usd": 0.42}


def test_a_final_status_cannot_be_changed():
    s, run_id = store_with_run()
    s.set_status(run_id, "revoked", "disabled", "t1")
    with pytest.raises(ValueError):
        s.set_status(run_id, "running", None, "t2")


def test_the_schema_refuses_unknown_statuses_and_outcomes():
    s, run_id = store_with_run()
    with pytest.raises(ValueError):
        s.set_status(run_id, "paused", None, "t1")
    seq, _ = s.begin_step(run_id, "k", "helper", "edit_file", "sha", "t1")
    with pytest.raises(ValueError):
        s.finish_step(run_id, seq, "maybe", None)
