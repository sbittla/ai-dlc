"""Provided: the bot's world for one repository (the web application stand-in, or Relay itself).

Everything a proposal needs is Relay's own code: the registry and token service (Chapter 14), the run store and
approval gate (Chapter 10), the effect ledger (Chapter 18) and the maintenance policy and desk (Chapter 19). The
code host is a recording fake that numbers pull requests from `first_pr`.
"""

from __future__ import annotations

import hashlib
import json

from . import DATA, RELAY  # noqa: F401  (puts Relay on the path)
from relay.agents import ApprovalGate, RunStore
from relay.agents.session import AgentSession
from relay.agentops.effects import EffectLedger
from relay.audit import AgentRegistry, AuditTrail, TokenService
from relay.maintenance import CodeOwners, ProposalDesk, load_file

PERSON_ISSUER = "https://login.relay.example"
GITHUB = "https://token.actions.githubusercontent.com"
SUBJECT = "repo:relay-example/relay:environment:maintenance"
POLICY = load_file(RELAY / "maintenance" / "policy.json")
T0 = 1_811_808_000.0  # 2027-06-01 00:00 UTC; the lab's clock counts seconds from here


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def read(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Clock:
    def __init__(self, t: float = T0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def stamp(self) -> str:
        return f"t+{self.t - T0:.0f}"


class World:
    def __init__(self, codeowners: str, first_pr: int = 412) -> None:
        self.clock = Clock()
        registry_data = json.loads((RELAY / "governance" / "agents.json").read_text(encoding="utf-8"))
        self.registry = AgentRegistry(registry_data)
        self.tokens = TokenService(self.registry, b"l" * 32, clock=self.clock, new_id=lambda: "jti-lab")
        self.trail = AuditTrail(clock=self.clock.stamp)
        self.store = RunStore()
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.ledger = EffectLedger(stamp=self.clock.stamp, clock=self.clock)
        self.session = AgentSession(self.tokens, "maintenance-bot", ["tasks:read:platform"], prove=self.proof)
        self.main = "base-0"   # the default branch's head on the fake code host
        self.desk = ProposalDesk(POLICY, CodeOwners(codeowners), self.gate, self.trail, self.ledger, self.session,
                                 self.clock.stamp, head=lambda: self.main)
        self.prs: list[dict] = []
        self.first_pr = first_pr

    def proof(self) -> dict:
        """The bot's own workload proof (its CI job's OIDC token, already verified)."""
        return {"iss": GITHUB, "sub": SUBJECT, "aud": "relay-token-exchange", "iat": self.clock()}

    def person(self, name: str) -> dict:
        """A person's own short-lived proof from the person issuer, issued now."""
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def run(self, task_id: str) -> str:
        run_id, _ = self.store.start_run(f"maint:{task_id}", task_id, "maintenance", "maintenance-bot",
                                         POLICY.bot_owner, self.clock.stamp())
        return run_id

    def open_pr(self, key: str, args: dict) -> dict:
        for p in self.prs:
            if p["key"] == key:
                return {"number": p["number"], "existing": True}
        self.prs.append({"key": key, "number": self.first_pr + len(self.prs)})
        return {"number": self.prs[-1]["number"], "existing": False}

    def refused(self) -> list[tuple[str, str]]:
        return [(r["action"], r["detail"].get("code")) for r in self.trail.records if r["outcome"] == "refused"]


def webapp_files(version: str) -> dict[str, str]:
    """The web application at one sessionkeel version, as the sandbox sees it."""
    return {"sessionkeel.py": read(f"packages/sessionkeel-{version}.py"), "signin.py": read("webapp/signin.py")}
