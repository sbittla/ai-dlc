"""The spec-to-PR helper built four ways: a workflow, a single agent, multiple agents, and the routed design.

Every design does the same job on the same task: read the approved task, change the listed files until
the approved tests and the suite pass, run the pre-review check, and open a draft pull request after the
requester approves it. Or, if the task cannot be done within its list of files, hand it back.

- `run_workflow`: deterministic code decides every step. The model is called at fixed points, with a
  context the code assembles: the listed files, the approved tests, and any unlisted file a listed file
  imports. Three attempts, then hand back (Chapter 9's stop signal).
- `run_single`: one agent in Relay's loop (`relay.agents.run_loop`), choosing its own tool calls. It can
  search, so it can find a file nobody listed. Its budget and stopping conditions are code.
- `run_multi`: a supervisor routes work to a planner, a coder, a tester and a reviewer, each a separate
  agent with its own identity, tools and context. Hand-offs are summaries, not transcripts.
- `run_routed`: the workflow first; if it hands back because its attempts failed, the single agent takes
  over with the workflow's notes. A hand-back for a file outside the list goes to a person, not an agent.
"""

from __future__ import annotations

from relay.agents import Decision, StepRecord, StopRules, run_loop, stop_reason

from .runtime import Runtime
from .world import marker

HELPER = "spec-to-pr-helper"
WORKFLOW_TOOLS = ["read_task", "read_file", "edit_file", "run_tests", "run_prcheck", "open_pull_request"]
AGENT_TOOLS = ["read_task", "read_file", "search_code", "edit_file", "run_tests", "run_prcheck", "open_pull_request"]
ROLES = {"sta-supervisor": ["open_pull_request"], "sta-planner": ["read_task", "read_file", "search_code"],
         "sta-coder": ["read_file", "edit_file"], "sta-tester": ["run_tests", "run_prcheck"],
         "sta-reviewer": ["read_file"]}
OUT_OF_SCOPE = "needs a file outside the task's list"


def pr_args(rt: Runtime) -> dict:
    t = rt.task
    return {"branch": f"agent/{t.task_id.lower()}", "title": f"{t.task_id}: {t.title}",
            "body": "Claims, each with file and line; approved tests unchanged; Docs: none."}


# ----------------------------------------------------------------------------- workflow

def run_workflow(rt: Runtime, design: dict) -> tuple[str, str]:
    """The deterministic design. Steps, all tool calls through rt.call on the helper's boundary:

    1. b = rt.boundary(HELPER, WORKFLOW_TOOLS, write=True); call read_task with the task's ID.
    2. Context: the task's files, then its tests file, then, if task.context_by_import, whichever of
       context_file and outside_file the task has (a listed file imports it). read_file each, in that order.
    3. has_context is True for a local task, and for a cross_file task whose context file was read in step 2.
       seen_outside is True for an out_of_scope task whose outside file was read in step 2.
       thread = rt.thread(tokens["system_workflow"] + tokens["task"] + the tokens of every context file).
    4. For k = 1 .. design["max_attempts"]:
         cannot = rt.sim.notices_out_of_scope(k, seen_outside)
         rt.model(HELPER, thread, out["hand_back"] if cannot else out["edit"] * number of files)
         if cannot: return ("handed_back", OUT_OF_SCOPE)
         variant = rt.sim.variant(k, has_context); edit_file every listed file, in order, with
         content marker(task_id, variant, k)
         tests = run_tests target "approved"; thread.add(rt.result_tokens("run_tests", tests))
         last = tests.failure
         if tests.failure is None: suite = run_tests target "suite"; last = suite.failure.
           If suite.failure is None: when design.get("review") is true and review_passes(rt, k, variant)
           is false, set last = "review:changes_requested", thread.add(out["review"]) and go to the
           next attempt; otherwise stop the loop. If the suite failed, thread.add(its result tokens).
       If no attempt got through: return ("handed_back", f"repeated_failure:{last}").
    5. return open_pr(rt, b): the pre-review check, the description and the pull request (provided).

    Here `out` is rt.cfg["tokens"]["out"] and `tokens` is rt.cfg["tokens"].
    """
    raise NotImplementedError("TODO 3: run_workflow (Lab 10.1 step 3)")


def review_passes(rt: Runtime, k: int, variant: str) -> bool:
    """The routed design's review step: one model call that reads the spec section and the diff (Chapter 7's
    LLM-as-judge, used as a check, not an approval). A rejection counts as a failed attempt."""
    tok, out, t = rt.cfg["tokens"], rt.cfg["tokens"]["out"], rt.task
    review = rt.thread(tok["system_workflow"] + tok["task"] + out["edit"] * len(t.files) + tok["tests_green"])
    rt.model(HELPER, review, out["review"])
    rejected = rt.sim.reviewer_rejects(k, variant)
    rt.history.append(StepRecord("review", not rejected, "review:changes_requested" if rejected else None,
                                 f"review:{k}"))
    return not rejected


def open_pr(rt: Runtime, b) -> tuple[str, str]:
    """Run the pre-review check, write the description (one model call) and open the pull request."""
    tok, out, t = rt.cfg["tokens"], rt.cfg["tokens"]["out"], rt.task
    rt.call(b, "run_prcheck", {})
    describe = rt.thread(tok["system_workflow"] + tok["task"] + out["edit"] * len(t.files) + tok["tests_green"])
    rt.model(HELPER, describe, out["describe"])
    rt.call(b, "open_pull_request", pr_args(rt))
    return "finished", "pull request opened"


# ----------------------------------------------------------------------------- single agent

class ScriptPolicy:
    """A simulated agent as a `relay.agents.loop.Policy`: a script of choices, played through Relay's loop.

    Each choice costs one model call on the agent's thread. Tool results are added to the thread, so the
    context grows as an agent's does. With probability p_invalid_args a choice is first made with a
    malformed argument, which the boundary refuses and the agent then corrects.
    """

    def __init__(self, rt: Runtime, actor: str, thread, script) -> None:
        self.rt, self.actor, self.thread = rt, actor, thread
        self.gen = script(self)
        self.started = False
        self.last = None
        self.retry = None
        self.pending: tuple[str, dict] | None = None
        self.n = 0
        self.variant = None

    def next_call(self) -> tuple[str, int, int, int]:
        return self.rt.cfg["model"], self.thread.next_input(), self.rt.cfg["tokens"]["max_output"], 0

    def decide(self) -> Decision:
        if self.retry is not None:
            action, tool, args, out, note = self.retry
            self.retry = None
        else:
            step = self.gen.send(self.last) if self.started else next(self.gen)
            self.started = True
            action, tool, args, out, note = step
            self.n += 1
            if action == "tool" and args and self.rt.sim.invalid_call(self.n, self.actor):
                self.retry = step
                key = sorted(args)[0]
                args = {**args, key: 42}  # a wrong type: the contract refuses it
        self.last = None
        usage = self.thread.call(out)
        self.rt.clock.advance(usage.seconds)
        self.thread.done_at(self.rt.clock())
        self.pending = (tool, args) if action == "tool" else None
        return Decision(action, self.rt.cfg["model"], usage.input_tokens, usage.output_tokens, usage.seconds,
                        usage.cached_tokens, tool=tool, args=args, note=note)

    def observe(self, tool: str, result) -> None:
        if result is not None:
            self.thread.add(self.rt.result_tokens(tool, result))
        if self.retry is None:
            self.last = result


def call(tool: str, args: dict, out: int) -> tuple:
    return ("tool", tool, args, out, "")


def agent_script(start_attempt: int = 1, opens_pr: bool = True):
    """The single agent's choices. A generator: each `yield` is one model call; it receives the tool result."""

    def script(p: ScriptPolicy):
        rt, t, sim = p.rt, p.rt.task, p.rt.sim
        out = rt.cfg["tokens"]["out"]
        yield call("read_task", {"task_id": t.task_id}, out["tool_call"])
        for path in list(t.files) + [t.tests]:
            yield call("read_file", {"path": path}, out["tool_call"])
        found: list[str] = []
        if sim.explores(t.context_by_import):
            r = yield call("search_code", {"pattern": t.symbol}, out["tool_call"])
            found = list(r.value) if r is not None and r.ok else []
            for path in found:
                yield call("read_file", {"path": path}, out["tool_call"])
        has_context = t.shape == "local" or (t.context_file is not None and t.context_file in found)
        seen_outside = t.outside_file is not None and t.outside_file in found
        k = start_attempt - 1
        while True:
            k += 1
            if sim.notices_out_of_scope(k, seen_outside):
                yield ("hand_back", None, {}, out["hand_back"], OUT_OF_SCOPE)
                return
            if seen_outside and sim.overreaches(k):  # tries to edit the file it may not touch; refused
                yield call("edit_file", {"path": t.outside_file, "content": marker(t.task_id, "wrong", k)},
                           out["edit"])
            variant = sim.variant(k, has_context)
            for path in t.files:
                yield call("edit_file", {"path": path, "content": marker(t.task_id, variant, k)}, out["edit"])
            r = yield call("run_tests", {"target": "approved"}, out["tool_call"])
            if r is not None and r.failure is None:
                r = yield call("run_tests", {"target": "suite"}, out["tool_call"])
                if r is not None and r.failure is None:
                    break
            if sim.rereads(k):
                yield call("read_file", {"path": t.files[0]}, out["tool_call"])
        if not opens_pr:  # the routed design's agent stops at a green branch; the workflow does the rest
            p.variant = variant
            yield ("finish", None, {}, out["finish"], "green branch")
            return
        yield call("run_prcheck", {}, out["tool_call"])
        yield ("tool", "open_pull_request", pr_args(rt), out["pull_request"], "")
        yield ("finish", None, {}, out["finish"], "pull request opened")

    return script


def run_single(rt: Runtime, design: dict, start_attempt: int = 1, notes: bool = False,
               opens_pr: bool = True) -> tuple[str, str]:
    tok = rt.cfg["tokens"]
    tools = AGENT_TOOLS if opens_pr else [n for n in AGENT_TOOLS if n != "open_pull_request"]
    b = rt.boundary(HELPER, tools, write=True)
    thread = rt.thread(tok["system_agent"] + tok["task"] + (tok["notes"] if notes else 0))
    policy = ScriptPolicy(rt, HELPER, thread, agent_script(start_attempt, opens_pr))
    rules = StopRules(**design["stop"])
    if opens_pr:
        done = lambda: bool(rt.github.pulls) and rt.sandbox.approved_pass()  # noqa: E731
    else:
        done = rt.sandbox.approved_pass
    result = run_loop(policy, b, rules, done)
    while result.status == "awaiting_approval":
        tool, args = policy.pending
        r = rt.approve_and_call(b, result.approval_id, tool, args)
        result.history.append(StepRecord(tool, r.ok, r.failure, r.progress))
        policy.observe(tool, r)
        result = run_loop(policy, b, rules, done, history=result.history)
    return result.status, result.reason


# ----------------------------------------------------------------------------- multiple agents

def run_multi(rt: Runtime, design: dict) -> tuple[str, str]:
    t, tok, sim = rt.task, rt.cfg["tokens"], rt.sim
    out = tok["out"]
    rules = StopRules(**design["stop"])
    b = {role: rt.boundary(role, tools, write=(role == "sta-coder")) for role, tools in ROLES.items()}
    threads = {role: rt.thread(tok["system_role"] + tok["task"]) for role in ROLES}
    sup = threads["sta-supervisor"]

    def route() -> None:
        rt.model("sta-supervisor", sup, out["route"])

    slips = {role: 0 for role in ROLES}

    def act(role: str, tool: str, args: dict):
        slips[role] += 1
        if args and sim.invalid_call(slips[role], role):  # a malformed first try, refused, then corrected
            rt.model(role, threads[role], out["tool_call"])
            bad = rt.call(b[role], tool, {**args, sorted(args)[0]: 42})
            threads[role].add(rt.result_tokens(tool, bad))
        rt.model(role, threads[role], out["tool_call"])
        r = rt.call(b[role], tool, args)
        threads[role].add(rt.result_tokens(tool, r))
        return r

    # planner
    route()
    act("sta-planner", "read_task", {"task_id": t.task_id})
    for path in list(t.files) + [t.tests]:
        act("sta-planner", "read_file", {"path": path})
    found: list[str] = []
    if sim.explores(t.context_by_import):
        r = act("sta-planner", "search_code", {"pattern": t.symbol})
        found = list(r.value) if r.ok else []
        for path in found:
            act("sta-planner", "read_file", {"path": path})
    planner_context = t.shape == "local" or (t.context_file is not None and t.context_file in found)
    seen_outside = t.outside_file is not None and t.outside_file in found
    if sim.notices_out_of_scope(1, seen_outside):
        rt.model("sta-planner", threads["sta-planner"], out["hand_back"])
        sup.add(tok["summary"])
        route()
        return "handed_back", OUT_OF_SCOPE
    rt.model("sta-planner", threads["sta-planner"], out["plan"])
    sup.add(tok["summary"])
    coder_context = t.shape == "local" or (planner_context and sim.handoff_keeps_context())
    coder, tester, reviewer = threads["sta-coder"], threads["sta-tester"], threads["sta-reviewer"]
    coder.add(tok["plan"])
    reviewer.add(tok["plan"])
    k = 0
    while True:
        reason = stop_reason(rt.meter, rt.history, rules)
        if reason is not None:
            return ("stopped" if reason.startswith("budget") else "handed_back"), reason
        k += 1
        route()
        if k == 1:
            for path in list(t.files) + [t.tests]:
                act("sta-coder", "read_file", {"path": path})
        if k > 1 and sim.notices_out_of_scope(k, False):
            rt.model("sta-coder", coder, out["hand_back"])
            sup.add(tok["summary"])
            route()
            return "handed_back", OUT_OF_SCOPE
        variant = sim.variant(k, coder_context)
        rt.model("sta-coder", coder, out["edit"] * len(t.files))
        for path in t.files:
            rt.call(b["sta-coder"], "edit_file", {"path": path, "content": marker(t.task_id, variant, k)})
        sup.add(tok["summary"])
        route()
        tests = act("sta-tester", "run_tests", {"target": "approved"})
        if tests.failure is None:
            tests = act("sta-tester", "run_tests", {"target": "suite"})
        rt.model("sta-tester", tester, out["report"])
        sup.add(tok["summary"])
        if tests.failure is not None:
            coder.add(tok["tests_red"])
            continue
        route()
        for path in t.files:
            act("sta-reviewer", "read_file", {"path": path})
        rt.model("sta-reviewer", reviewer, out["review"])
        sup.add(tok["summary"])
        if sim.reviewer_rejects(k, variant):
            rt.history.append(StepRecord("review", False, "review:changes_requested", f"review:{k}"))
            coder.add(out["review"])
            continue
        break
    route()
    act("sta-tester", "run_prcheck", {})
    rt.model("sta-supervisor", sup, out["pull_request"])
    rt.call(b["sta-supervisor"], "open_pull_request", pr_args(rt))
    return "finished", "pull request opened"


# ----------------------------------------------------------------------------- routed

def run_routed(rt: Runtime, design: dict) -> tuple[str, str]:
    review = design.get("review", True)
    status, reason = run_workflow(rt, {**design["workflow"], "review": review})
    if status != "handed_back" or not reason.startswith("repeated_failure"):
        return status, reason
    first = design["workflow"]["max_attempts"] + 1
    rt.escalated = True
    status, reason = run_single(rt, design["agent"], start_attempt=first, notes=True, opens_pr=False)
    if status != "finished":
        return status, reason
    if review and not review_passes(rt, first, rt.sandbox.variant()):
        return "handed_back", "review:changes_requested"
    b = rt.boundary(HELPER, WORKFLOW_TOOLS, write=True)
    return open_pr(rt, b)


DESIGN_FUNCTIONS = {"workflow": run_workflow, "single": run_single, "multi": run_multi, "routed": run_routed}
