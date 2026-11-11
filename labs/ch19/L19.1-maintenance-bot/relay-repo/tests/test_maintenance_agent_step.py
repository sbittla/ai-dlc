"""The maintenance bot's one agent step behind Chapter 10's boundary (4.31.0, ADR-053): a steered model is
refused at the boundary, every refusal is audited, and a legitimate edit still works. The report bodies are
inert labelled placeholders, and the model is a script."""

from maintenance_helpers import POLICY, World
from relay.agents import Budget, Decision, Meter, StopRules, ToolBoundary, ToolOutput, run_loop
from relay.maintenance.agent_step import step_tools

INERT = "[[INERT-INJECTION-PLACEHOLDER asks-for: edit-workflow, edit-instructions, approve-own-pr]]"


class Script:
    actor = "maintenance-bot"

    def __init__(self, moves):
        self.moves = list(moves)
        self.seen = []

    def next_call(self):
        return "sim-large", 2000, 400, 0

    def decide(self):
        action, tool, args = self.moves.pop(0)
        return Decision(action, "sim-large", 2000, 300, 2.0, tool=tool, args=args or {}, note="done")

    def observe(self, tool, result):
        self.seen.append((tool, getattr(result, "ok", None), getattr(result, "code", None)))


def boundary(w: World, task_type="docs-upkeep", task_files=("docs/integrations.md", ".github/workflows/maintenance.yml",
                                                             "AGENTS.md")):
    files = {"docs/integrations.md": "See https://relay.example/old-path for details.\n"}
    run_id = w.run("DU-7")
    contracts, handlers, write, derive = step_tools(
        POLICY, task_type, list(task_files), files, {"ISS-7": INERT},
        lambda a: ToolOutput({"status": "ok"}, 3.0, progress="tests:ok"))
    b = ToolBoundary(run_id, "maintenance-bot", contracts, handlers, w.session,
                     Meter(Budget(max_steps=20, max_usd=0.30, max_seconds=600)), w.store, w.trail, w.gate,
                     write, w.clock.stamp, derive=derive)
    return b, files


def test_the_write_list_never_includes_a_protected_path_even_if_the_task_names_one():
    w = World()
    b, _ = boundary(w)
    assert b.write_paths == frozenset({"docs/integrations.md"})


def test_a_steered_step_is_refused_at_every_attempt_and_each_refusal_is_audited():
    w = World()
    b, files = boundary(w)
    script = Script([
        ("tool", "read_report", {"report_id": "ISS-7"}),
        ("tool", "edit_file", {"path": ".github/workflows/maintenance.yml", "content": "PLACEHOLDER"}),
        ("tool", "edit_file", {"path": "AGENTS.md", "content": "PLACEHOLDER"}),
        ("tool", "approve_pull_request", {"number": 3100}),
        ("tool", "open_pull_request", {"branch": "x", "title": "x", "body": "x"}),
        ("hand_back", None, None)])
    result = run_loop(script, b, StopRules(), done_check=lambda: False)
    assert result.status == "handed_back" and b.tainted
    assert [s[2] for s in script.seen[1:]] == ["path_not_allowed", "path_not_allowed", "unknown_tool", "unknown_tool"]
    refused = [r["detail"]["code"] for r in w.trail.records if r["outcome"] == "refused"]
    assert refused == ["path_not_allowed", "path_not_allowed", "unknown_tool", "unknown_tool"]
    assert set(files) == {"docs/integrations.md"}


def test_three_identical_refusals_stop_the_step():
    w = World()
    b, _ = boundary(w)
    bad = ("tool", "edit_file", {"path": "AGENTS.md", "content": "PLACEHOLDER"})
    result = run_loop(Script([("tool", "read_report", {"report_id": "ISS-7"}), bad, bad, bad, bad]), b, StopRules(),
                      done_check=lambda: False)
    assert (result.status, result.reason) == ("handed_back", "repeated_failure:refused:path_not_allowed")


def test_a_legitimate_documentation_fix_still_goes_through():
    w = World()
    b, files = boundary(w)
    new = "See https://relay.example/docs/integrations for details.\n"
    script = Script([("tool", "read_report", {"report_id": "ISS-7"}),
                     ("tool", "read_file", {"path": "docs/integrations.md"}),
                     ("tool", "edit_file", {"path": "docs/integrations.md", "content": new}),
                     ("tool", "run_tests", {"target": "suite"}),
                     ("finish", None, None)])
    result = run_loop(script, b, StopRules(), done_check=lambda: files["docs/integrations.md"] == new)
    assert result.status == "finished" and [s[1] for s in script.seen] == [True, True, True, True]
