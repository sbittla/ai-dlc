"""Provided: run one adversarial record against Relay's controls, and return what happened as a short code.

Each record is a labelled, inert placeholder: it names the action an attacker's text would ask for, and the
scripted model (or the caller) performs exactly that action. What is tested is the control, not a model's
willingness to obey.
"""

from __future__ import annotations

import json

from . import DATA, RELAY  # noqa: F401  (puts Relay on the path)
from relay.agents import (ApprovalGate, ApprovalRefused, Budget, Decision, Meter, RunStore, StopRules, ToolBoundary,
                          ToolOutput, request_budget_raise, run_loop)
from relay.agents.session import AgentSession
from relay.agentops.effects import EffectLedger
from relay.agentops.jobs import AgentJobQueue
from relay.audit import AgentRegistry, AuditTrail, TokenService
from relay.maintenance import Bundle, Check, CodeOwners, ProposalDesk, ProposalRefused, Report, item, load_file
from relay.maintenance import reproduce, triage
from relay.maintenance.agent_step import step_tools
from relay.maintenance.longrun import Campaign

PERSON_ISSUER = "https://login.relay.example"
SUBJECT = "repo:relay-example/relay:environment:maintenance"
POLICY = load_file(RELAY / "maintenance" / "policy.json")
GOOD = Bundle((item("E1", "tests pass", Check("t", "pass", "")),))


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class Clock:
    def __init__(self, t: float = 1_814_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def stamp(self) -> str:
        return f"t+{self.t - 1_814_000_000.0:.0f}"


class World:
    def __init__(self) -> None:
        self.clock = Clock()
        self.main = "base-0"
        data = json.loads((RELAY / "governance" / "agents.json").read_text(encoding="utf-8"))
        self.registry = AgentRegistry(data)
        self.tokens = TokenService(self.registry, b"c" * 32, clock=self.clock, new_id=lambda: "jti-case")
        self.trail = AuditTrail(clock=self.clock.stamp)
        self.store = RunStore()
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.session = AgentSession(self.tokens, "maintenance-bot", ["tasks:read:platform"], prove=self.proof)
        self.desk = ProposalDesk(POLICY, CodeOwners((RELAY / ".github" / "CODEOWNERS").read_text(encoding="utf-8")),
                                 self.gate, self.trail, EffectLedger(stamp=self.clock.stamp, clock=self.clock),
                                 self.session, self.clock.stamp, head=lambda: self.main)

    def proof(self) -> dict:
        return {"iss": "https://token.actions.githubusercontent.com", "sub": SUBJECT, "aud": "relay-token-exchange",
                "iat": self.clock()}

    def person(self, name: str) -> dict:
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def run(self, task: str) -> str:
        return self.store.start_run(f"maint:{task}", task, "maintenance", "maintenance-bot", POLICY.bot_owner,
                                    self.clock.stamp())[0]

    def audited_refusals(self) -> int:
        return sum(1 for r in self.trail.records if r["outcome"] == "refused")


class Script:
    actor = "maintenance-bot"

    def __init__(self, moves):
        self.moves, self.seen = list(moves), []

    def next_call(self):
        return "sim-large", 4000, 800, 0

    def decide(self):
        action, tool, args = self.moves.pop(0)
        return Decision(action, "sim-large", 4000, 600, 2.0, tool=tool, args=args or {}, note="steered")

    def observe(self, tool, result):
        self.seen.append(result)


def _step(w: World, record: dict, budget: Budget | None = None):
    files = {"docs/integrations.md": "old\n"}
    body = record["body"] + ("x" * record.get("size", 0))
    task_files = ["docs/integrations.md"]
    if record.get("call") and record["call"][0] == "edit_file":
        task_files.append(record["call"][1]["path"])     # the task names the path: only the policy can refuse it
    contracts, handlers, write, derive = step_tools(POLICY, "docs-upkeep", task_files, files,
                                                    {record["id"]: body},
                                                    lambda a: ToolOutput({"status": "ok"}, 3.0, progress="t"))
    boundary = ToolBoundary(w.run(record["id"]), "maintenance-bot", contracts, handlers, w.session,
                            Meter(budget or Budget(max_steps=20, max_usd=0.30, max_seconds=600)), w.store, w.trail,
                            w.gate, write, w.clock.stamp, derive=derive)
    return boundary, files


def run_record(record: dict) -> tuple[str, int]:
    """(outcome code, audited refusals) for one adversarial record."""
    w = World()
    kind = record["kind"]
    if kind == "step":
        boundary, _ = _step(w, record)
        tool, args = record["call"]
        script = Script([("tool", "read_report", {"report_id": record["id"]}), ("tool", tool, args),
                         ("hand_back", None, {})])
        run_loop(script, boundary, StopRules(), done_check=lambda: False)
        return script.seen[1].code or "ok", w.audited_refusals()
    if kind == "oversize":
        boundary, _ = _step(w, record)
        result = boundary.call("read_report", {"report_id": record["id"]})
        return ("truncated" if result.truncated else "whole"), w.audited_refusals()
    if kind == "triage":
        t = triage(Report(record["id"], "issue-form", record["form"], record["body"]), {})
        return t.task_type or "person", 0
    if kind == "sandbox":
        r = reproduce({"keel.py": "x = 1\n"}, None, record["code"])
        return r.outcome, 0
    if kind in ("approve", "swap", "stale"):
        p = w.desk.propose(w.run(record["id"] + "-p"), record["id"], "docs-upkeep",
                           {"docs/integrations.md": "fixed"}, [], GOOD)
        if kind == "stale":
            w.desk.decide(p.proposal_id, w.person("sam.o"), True, "ok")
            w.clock.t += 3 * 24 * 3600
            try:
                w.desk.open_pull_request(p.proposal_id, {"docs/integrations.md": "fixed"}, GOOD.sha256(),
                                         lambda k, a: {"number": 1})
                return "opened", w.audited_refusals()
            except ProposalRefused as exc:
                return exc.code, w.audited_refusals()
        if kind == "swap":
            w.desk.decide(p.proposal_id, w.person("sam.o"), True, "ok")
            try:
                w.desk.open_pull_request(p.proposal_id, {"docs/integrations.md": "changed after approval"},
                                         GOOD.sha256(), lambda k, a: {"number": 1})
                return "opened", w.audited_refusals()
            except ProposalRefused as exc:
                return exc.code, w.audited_refusals()
        proof = w.proof() if record["approver"] == "bot" else w.person(record["approver"])
        try:
            w.desk.decide(p.proposal_id, proof, True, "ok")
            return "approved", w.audited_refusals()
        except ApprovalRefused as exc:
            return exc.code, w.audited_refusals()
    if kind == "propose":
        try:
            w.desk.propose(w.run(record["id"]), record["id"], "docs-upkeep", {p: "PLACEHOLDER" for p in record["paths"]},
                           [], GOOD)
            return "proposed", w.audited_refusals()
        except ProposalRefused as exc:
            return exc.code, w.audited_refusals()
    if kind == "raise":
        c = Campaign(record["id"], w.store, AgentJobQueue(), w.trail, w.gate, "maintenance-bot", POLICY.bot_owner,
                     POLICY.bot_owner, w.clock.stamp)
        c.start([{"item_id": "i1", "estimate_usd": 0.01}], Budget(max_steps=5, max_usd=0.01, max_seconds=60), w.clock())
        a = request_budget_raise(w.gate, c.run_id, {"max_steps": 5, "max_usd": 1.0, "max_seconds": 60},
                                 "maintenance-bot", POLICY.bot_owner)
        try:
            c.decide_raise(a.approval_id, w.person(POLICY.bot_owner), True, "more")
            return "raised", w.audited_refusals()
        except ApprovalRefused as exc:
            return exc.code, w.audited_refusals()
    raise ValueError(f"unknown kind {kind!r}")
