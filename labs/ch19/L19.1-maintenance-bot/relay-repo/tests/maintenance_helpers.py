"""Shared set-up for the relay.maintenance tests (4.31.0): the committed policy and CODEOWNERS, the maintenance
bot's own registry entry, a clock, an audit trail, an approval gate, an effect ledger and a recording code host."""

from __future__ import annotations

import json
from pathlib import Path

from relay.agents import ApprovalGate, RunStore
from relay.agents.session import AgentSession
from relay.agentops.effects import EffectLedger
from relay.audit import AgentRegistry, AuditTrail, TokenService
from relay.maintenance import CodeOwners, ProposalDesk, load_file

ROOT = Path(__file__).resolve().parent.parent
PERSON_ISSUER = "https://login.relay.example"
GITHUB = "https://token.actions.githubusercontent.com"
SUBJECT = "repo:relay-example/relay:environment:maintenance"
REGISTRY = json.loads((ROOT / "governance" / "agents.json").read_text(encoding="utf-8"))
POLICY = load_file(ROOT / "maintenance" / "policy.json")
OWNERS = CodeOwners((ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8"))


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
        self.registry = AgentRegistry(REGISTRY)
        self.tokens = TokenService(self.registry, b"m" * 32, clock=self.clock, new_id=lambda: "jti-m")
        self.trail = AuditTrail(clock=self.clock.stamp)
        self.store = RunStore()
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.ledger = EffectLedger(stamp=self.clock.stamp, clock=self.clock)
        self.session = AgentSession(self.tokens, "maintenance-bot", ["tasks:read:platform"], prove=self.proof)
        self.main = "c0ffee1"   # the default branch's head, as the code host reports it
        self.desk = ProposalDesk(POLICY, OWNERS, self.gate, self.trail, self.ledger, self.session, self.clock.stamp,
                                 head=lambda: self.main)
        self.prs: list[dict] = []

    def proof(self) -> dict:
        return {"iss": GITHUB, "sub": SUBJECT, "aud": "relay-token-exchange", "iat": self.clock()}

    def person(self, name: str) -> dict:
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def run(self, task_id: str) -> str:
        run_id, _ = self.store.start_run(f"maint:{task_id}", task_id, "maintenance", "maintenance-bot", "priya.n",
                                         self.clock.stamp())
        return run_id

    def open_pr(self, key: str, args: dict) -> dict:
        existing = [p for p in self.prs if p["key"] == key]
        if existing:
            return {"number": existing[0]["number"], "existing": True}
        self.prs.append({"key": key, "number": 3100 + len(self.prs)})
        return {"number": self.prs[-1]["number"], "existing": False}

    def refusals(self, action: str) -> list[str]:
        return [r["detail"].get("code") for r in self.trail.records if r["action"] == action
                and r["outcome"] == "refused"]
