"""Shared set-up for the relay.agents tests (4.24.0): a registry with one helper agent, a clock and a run."""

from __future__ import annotations

import hashlib
import json

from relay.agents import ApprovalGate, Budget, Meter, RunStore, ToolBoundary, ToolOutput
from relay.agents.session import AgentSession
from relay.audit import AuditTrail, AgentRegistry, TokenService

PERSON_ISSUER = "https://login.relay.example"
GITHUB = "https://token.actions.githubusercontent.com"
KEY = b"k" * 32

REGISTRY = {
    "version": "test", "people": ["priya.n", "sam.o", "aisha.r"], "person_issuer": PERSON_ISSUER,
    "agents": [{"agent_id": "spec-to-pr-helper", "kind": "ci-job", "owner": "sam.o", "issuer": GITHUB,
                "subject": "repo:relay-example/relay:environment:spec-to-pr", "cloud_role": None,
                "scopes": ["tasks:read:platform"], "max_ttl_seconds": 900, "delegation": "required",
                "delegators": ["priya.n", "sam.o"], "github_app": "relay-spec-to-pr"}],
}


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def stamp(self) -> str:
        return f"t+{self.t - 1_800_000_000.0:.0f}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class World:
    """One run of the helper agent with a recording fake GitHub and a sandbox of files."""

    def __init__(self, budget: Budget | None = None, contracts=None, write_paths=("src/relay/x.py",)) -> None:
        from relay.agents import HELPER_TOOLS
        self.clock = Clock()
        self.registry = AgentRegistry(REGISTRY)
        self.tokens = TokenService(self.registry, KEY, clock=self.clock, new_id=lambda: "jti-1")
        self.trail = AuditTrail(clock=self.clock.stamp)
        self.store = RunStore()
        self.run_id, _ = self.store.start_run("req-1", "T-001", "workflow", "spec-to-pr-helper", "priya.n",
                                              self.clock.stamp())
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.meter = Meter(budget or Budget(max_steps=50, max_usd=5.0, max_seconds=1800))
        self.session = AgentSession(self.tokens, "spec-to-pr-helper", ["tasks:read:platform"],
                                    prove=self.proof, subject=lambda: self.person("priya.n"))
        self.prs: list[dict] = []
        self.files = {"src/relay/x.py": "old\n"}
        self.search_hits = ["src/relay/y.py"]
        handlers = {
            "read_task": lambda a: ToolOutput({"task": a["task_id"]}, 0.1),
            "read_file": lambda a: ToolOutput(self.files.get(a["path"], ""), 0.1, progress="read:" + a["path"]),
            "search_code": lambda a: ToolOutput(list(self.search_hits), 0.2),
            "edit_file": self.edit,
            "run_tests": lambda a: ToolOutput("1 failed", 8.0, failure="tests:test_a", progress="tests:red"),
            "run_prcheck": lambda a: ToolOutput("0 findings", 2.0),
            "open_pull_request": self.open_pr,
        }
        derive = {"edit_file": lambda a: {"before_sha256": sha(self.files.get(a["path"], ""))},
                  "open_pull_request": lambda a: {"diff_sha256": self.diff_sha()}}
        self.boundary = ToolBoundary(self.run_id, "spec-to-pr-helper", contracts or HELPER_TOOLS, handlers,
                                     self.session, self.meter, self.store, self.trail, self.gate,
                                     frozenset(write_paths), self.clock.stamp, derive=derive)

    def diff_sha(self) -> str:
        return sha(json.dumps(self.files, sort_keys=True))

    def proof(self) -> dict:
        return {"iss": GITHUB, "sub": "repo:relay-example/relay:environment:spec-to-pr",
                "aud": "relay-token-exchange", "iat": self.clock()}

    def person(self, name: str) -> dict:
        """The person's own short-lived proof, issued now (Chapter 14's subject token)."""
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def edit(self, args: dict) -> ToolOutput:
        self.files[args["path"]] = args["content"]
        return ToolOutput("edited", 0.1, progress="diff:" + args["content"])

    def open_pr(self, args: dict) -> ToolOutput:
        """Like GitHub: at most one open pull request per head branch; a repeat returns the existing one."""
        existing = [p for p in self.prs if p["branch"] == args["branch"]]
        if existing:
            return ToolOutput({"number": existing[0]["number"], "existing": True}, 1.0)
        self.prs.append({"branch": args["branch"], "number": 100 + len(self.prs), "diff": self.diff_sha()})
        return ToolOutput({"number": self.prs[-1]["number"], "existing": False}, 1.5)


PR_ARGS = {"branch": "agent/T-001", "title": "T-001", "body": "Claims: ..."}
