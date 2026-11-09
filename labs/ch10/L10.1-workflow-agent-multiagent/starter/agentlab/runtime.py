"""One run's Relay runtime: identities, tokens, audit trail, run state, approval gate and meter (provided).

Everything a design does goes through Relay 4.24.0's `relay.agents`: every tool call through a
`ToolBoundary` under the calling agent's own identity, every model call through the run's `Meter`. The
clock is simulated, so tokens expire and caches lapse in simulated time.

Approvals are given by a simulated requester (the person the run acts for), who approves every pull
request whose pre-review check has no blocking finding, with a fresh person proof as Chapter 14 requires.
The run's own token is exchanged once, at the start, with the requester's proof from the trigger: every
design's time budget is under the token's 15 minutes, so no run needs a second exchange. Time spent waiting for that approval is not
counted in a run's latency: the lab reports agent time only. A real reviewer reads the pull request
afterwards; that review is not simulated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from relay.agents import (ApprovalGate, AwaitingApproval, Budget, BudgetExceeded, HELPER_TOOLS, Meter, RunStore,
                          StepRecord, ToolBoundary, ToolOutput)
from relay.agents.session import AgentSession
from relay.audit import AgentRegistry, AuditTrail, TokenService, verify

from .sim import SimModel, Thread
from .world import GitHub, Sandbox, Task

EPOCH = 1_800_000_000.0  # simulated start of every run
KEY = b"lab-10-1-signing-key-not-a-secret!"
REQUESTER = "priya.n"
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"


class SimClock:
    def __init__(self) -> None:
        self.t = EPOCH

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds

    def stamp(self) -> str:
        return f"T+{self.t - EPOCH:09.3f}s"


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class RunRecord:
    task_id: str
    family: str
    shape: str
    difficulty: str
    design: str
    run: int
    status: str
    reason: str
    pr_opened: bool
    variant: str
    success: bool
    wrong_pr: bool
    usd: float
    seconds: float
    model_calls: int
    tool_calls: int
    steps: int
    refusals: dict
    redundant_reads: int
    approvals: int
    trail_ok: bool
    policy_ok: bool
    by_actor: dict = field(default_factory=dict)
    escalated: bool = False


class Runtime:
    def __init__(self, task: Task, run: int, design: str, cfg: dict, budget: Budget, registry: dict) -> None:
        self.task, self.run, self.design, self.cfg = task, run, design, cfg
        self.clock = SimClock()
        self.registry = AgentRegistry(registry)
        counter = iter(range(1, 1_000_000))
        self.tokens = TokenService(self.registry, KEY, clock=self.clock, new_id=lambda: f"jti-{next(counter)}")
        self.trail = AuditTrail(clock=self.clock.stamp)
        self.store = RunStore()
        self.run_id, _ = self.store.start_run(f"{design}:{task.task_id}:{run}", task.task_id, design,
                                              "spec-to-pr-helper", REQUESTER, self.clock.stamp())
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 self.registry.person_issuer)
        self.person_proof = self._fresh_person()  # sent with the trigger; used for the first exchange
        self.meter = Meter(budget)
        self.sim = SimModel(cfg, task, run)
        self.github = GitHub()
        self.sandbox = Sandbox(task, cfg, self.github, self.sim.suite_catches_hack())
        self.boundaries: dict[str, ToolBoundary] = {}
        self.sessions: dict[str, AgentSession] = {}
        self.approvals = 0
        self.escalated = False
        self.history: list[StepRecord] = []

    # identities and boundaries ------------------------------------------------
    def _proof(self, agent_id: str):
        agent = self.registry.get(agent_id)
        return lambda: {"iss": agent.issuer, "sub": agent.subject, "aud": "relay-token-exchange", "iat": self.clock()}

    def _fresh_person(self) -> dict:
        return {"iss": self.registry.person_issuer, "sub": REQUESTER, "aud": "relay-token-exchange",
                "iat": self.clock()}

    def _person(self) -> dict:
        return self.person_proof

    def boundary(self, agent_id: str, tools: list[str], write: bool) -> ToolBoundary:
        key = f"{agent_id}:{','.join(tools)}"
        if key in self.boundaries:
            return self.boundaries[key]
        agent = self.registry.get(agent_id)
        if agent_id not in self.sessions:
            self.sessions[agent_id] = AgentSession(
                self.tokens, agent_id, sorted(agent.scopes), prove=self._proof(agent_id),
                subject=self._person if agent.delegation == "required" else None)
            self.sessions[agent_id].verify(None)  # exchange now, while the trigger's person proof is fresh
        session = self.sessions[agent_id]
        handlers = {}
        for name, fn in self.sandbox.handlers().items():
            if name in tools:
                handlers[name] = self._timed(fn)
        contracts = {n: HELPER_TOOLS[n] for n in tools}
        sb = self.sandbox
        derive = {"edit_file": lambda a: {"before_sha256": sb.content_sha(a["path"])},
                  "open_pull_request": lambda a: {"diff_sha256": sb.diff_sha()}}
        b = ToolBoundary(self.run_id, agent_id, contracts, handlers, session, self.meter, self.store, self.trail,
                         self.gate, frozenset(self.task.files if write else ()), self.clock.stamp, derive=derive)
        self.boundaries[key] = b
        return b

    def _timed(self, fn):
        def run(args: dict) -> ToolOutput:
            out = fn(args)
            self.clock.advance(out.seconds)
            return out
        return run

    # calls -----------------------------------------------------------------------
    def call(self, boundary: ToolBoundary, tool: str, args: dict):
        """A tool call by deterministic code (a workflow step, an orchestrator), with approvals resolved."""
        try:
            result = boundary.call(tool, args)
        except AwaitingApproval as exc:
            result = self.approve_and_call(boundary, exc.approval_id, tool, args)
        self.history.append(StepRecord(tool, result.ok, result.failure, result.progress))
        return result

    def approve_and_call(self, boundary: ToolBoundary, approval_id: str, tool: str, args: dict):
        """The simulated requester approves; the paused step then runs once, as a resumed run would."""
        self.store.set_status(self.run_id, "awaiting_approval", tool, self.clock.stamp())
        proof = self._fresh_person()  # the requester's own proof, issued when they click approve
        self.gate.decide(approval_id, proof, True, "simulated requester: pre-review check has no blocking finding")
        self.person_proof = proof
        self.approvals += 1
        self.store.set_status(self.run_id, "running", None, self.clock.stamp())
        return boundary.call(tool, args)

    def thread(self, base_tokens: int, caching: bool = True) -> Thread:
        return Thread(self.cfg, self.clock, base_tokens, caching)

    def model(self, actor: str, thread: Thread, output_tokens: int) -> None:
        """One model call on `thread` by `actor`, admitted against and charged to the run's budget."""
        model = self.cfg["model"]
        self.meter.admit(self.meter.estimate(model, thread.next_input(), self.cfg["tokens"]["max_output"]))
        usage = thread.call(output_tokens)
        self.meter.charge_model(actor, model, usage.input_tokens, usage.output_tokens, usage.seconds,
                                usage.cached_tokens)
        self.clock.advance(usage.seconds)
        thread.done_at(self.clock())

    def result_tokens(self, tool: str, result) -> int:
        t = self.cfg["tokens"]
        if not result.ok:
            return t["refusal"]
        if tool == "read_file":
            return int(str(result.value).split(" ")[0].lstrip("<"))
        if tool == "run_tests":
            return t["tests_red"] if result.failure else t["tests_green"]
        return t["result"].get(tool, t["refusal"])

    # outcome ---------------------------------------------------------------------
    def record(self, status: str, reason: str) -> RunRecord:
        final = {"finished": "finished", "handed_back": "handed_back", "stopped": "stopped",
                 "revoked": "revoked", "delegation_expired": "delegation_expired"}.get(status, "failed")
        self.store.set_status(self.run_id, final, reason, self.clock.stamp())
        steps = self.store.steps(self.run_id)
        pr = bool(self.github.pulls)
        variant = self.sandbox.variant()
        if self.task.shape == "out_of_scope":
            success = not pr and status == "handed_back"
        else:
            success = pr and variant == "correct"
        reads = [s["args_sha256"] for s in steps if s["tool"] == "read_file" and s["outcome"] == "ok"]
        refusals: dict[str, int] = {}
        for b in self.boundaries.values():
            for code, n in b.refusals.items():
                refusals[code] = refusals.get(code, 0) + n
        return RunRecord(
            task_id=self.task.task_id, family=self.task.family, shape=self.task.shape,
            difficulty=self.task.difficulty, design=self.design, run=self.run, status=status, reason=reason,
            pr_opened=pr, variant=variant, success=success, wrong_pr=pr and variant != "correct",
            usd=round(self.meter.usd, 6), seconds=round(self.meter.seconds, 3), model_calls=self.meter.model_calls,
            tool_calls=self.meter.steps - self.meter.model_calls, steps=self.meter.steps, refusals=refusals,
            redundant_reads=len(reads) - len(set(reads)), approvals=self.approvals,
            trail_ok=verify(self.trail.records).ok, policy_ok=policy_ok(self.trail.records, self.github.pulls),
            by_actor={k: round(v, 6) for k, v in self.meter.by_actor.items()}, escalated=self.escalated)


def policy_ok(records: list[dict], pulls: list[dict]) -> bool:
    """Every pull request on GitHub carries a diff that a person approved, before it was opened.

    The diff is what GitHub holds for the pull request, not what any agent said. The approved diffs are
    read from the audit trail: an `approval.request` names the diff it is bound to, and an `approval.decide`
    with outcome approved accepts it. Every `tool.open_pull_request` record with outcome ok must also follow
    an approval of its exact arguments.
    """
    bound: dict[str, str] = {}
    requested: dict[str, str] = {}
    approved_args: set[str] = set()
    approved_diffs: set[str] = set()
    for r in records:
        d = r["detail"]
        if r["action"] == "approval.request":
            requested[d["approval_id"]] = d["args_sha256"]
            bound[d["approval_id"]] = d.get("bound", {}).get("diff_sha256", "")
        elif r["action"] == "approval.decide" and r["outcome"] == "approved":
            approved_args.add(requested.get(d["approval_id"], ""))
            approved_diffs.add(bound.get(d["approval_id"], ""))
        elif r["action"] == "tool.open_pull_request" and r["outcome"] == "ok":
            if d["args_sha256"] not in approved_args:
                return False
    return all(p["diff_sha256"] in approved_diffs for p in pulls)


def stopped_by(exc: BudgetExceeded) -> tuple[str, str]:
    return "stopped", f"budget:{exc.kind}"
