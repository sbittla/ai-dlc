"""Shared set-up for the relay.agentops tests (4.30.0): the spec-to-PR helper as a queue worker, with a scripted
policy standing in for the model, a fake code host that looks before it creates, the real sandbox, the shared
registry and the effect ledger. Every process-level object can be rebuilt on the same files, which is how the
tests stand in for a worker that dies and another that takes over."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from relay.agents import ApprovalGate, Budget, Decision, Meter, RunStore, StopRules, ToolBoundary, ToolOutput
from relay.agents.session import AgentSession
from relay.agentops import AgentJobQueue, CircuitBreaker, EffectLedger, SandboxPolicy, SharedRegistry
from relay.agentops.resilience import RateLimited
from relay.agentops.tools import PRODUCTION_HELPER_TOOLS, ledgered_pull_request, sandboxed_tests
from relay.agentops.worker import AgentKind, AgentWorker, decide_and_wake, run_agent
from relay.audit import AuditTrail, TokenService

PERSON_ISSUER = "https://login.relay.example"
GITHUB = "https://token.actions.githubusercontent.com"
KEY = b"k" * 32
T0 = 1_800_000_000.0
REGISTRY = {
    "version": "test", "people": ["priya.n", "sam.o", "aisha.r"], "person_issuer": PERSON_ISSUER,
    "agents": [{"agent_id": "spec-to-pr-helper", "kind": "ci-job", "owner": "sam.o", "issuer": GITHUB,
                "subject": "repo:relay-example/relay:environment:spec-to-pr", "cloud_role": None,
                "scopes": ["tasks:read:platform"], "max_ttl_seconds": 900, "delegation": "required",
                "delegators": ["priya.n", "sam.o"], "github_app": "relay-spec-to-pr"}],
}
RUNNER = "import tests_approved\nraise SystemExit(tests_approved.main())\n"
GOOD_CODE = "def add(a, b):\n    return a + b\n"
APPROVED_TEST = ("from feature import add\n\ndef main():\n    assert add(2, 3) == 5\n    print('1 passed')\n"
                 "    return 0\n")


class Clock:
    def __init__(self, t: float = T0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def stamp(self) -> str:
        return f"t+{self.t - T0:.0f}"


class SimulatedCrash(BaseException):
    """The worker process dies here. BaseException, so nothing in the worker catches it."""


class FakeGitHub:
    """At most one open pull request per branch; looks before it creates. Can crash after creating, once."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            path.write_text(json.dumps({"prs": [], "creates": 0}), encoding="utf-8")
        self.crash_after_create = False

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def prs(self) -> list[dict]:
        return self._load()["prs"]

    @property
    def creates(self) -> int:
        return self._load()["creates"]

    def open_pr(self, key: str, args: dict) -> dict:
        data = self._load()
        existing = [p for p in data["prs"] if p["key"] == key]
        if existing:
            return {"number": existing[0]["number"], "existing": True}
        number = 5100 + len(data["prs"])
        data["prs"].append({"key": key, "branch": args["branch"], "number": number})
        data["creates"] += 1
        self.path.write_text(json.dumps(data), encoding="utf-8")
        if self.crash_after_create:
            self.crash_after_create = False
            raise SimulatedCrash("worker died after the code host created the pull request")
        return {"number": number, "existing": False}


class HelperScript:
    """A scripted stand-in for the model: read, edit, test, open a pull request, finish. Its position is its state."""

    actor = "spec-to-pr-helper"

    def __init__(self, task_id: str, code: str, position: int = 0) -> None:
        self.task_id, self.code, self.position = task_id, code, position
        self.model_error = None  # an exception to raise on the next decide, for fault injection

    def plan(self) -> list:
        return [("read_task", {"task_id": self.task_id}), ("read_file", {"path": "src/relay/feature.py"}),
                ("edit_file", {"path": "src/relay/feature.py", "content": self.code}),
                ("run_tests", {"target": "approved"}),
                ("open_pull_request", {"branch": f"agent/{self.task_id}", "title": self.task_id,
                                       "body": "Claims: ..."}),
                ("finish", {})]

    def state(self) -> dict:
        return {"position": self.position}

    def next_call(self):
        return "sim-large", 2000, 512, 0

    def decide(self) -> Decision:
        if self.model_error is not None:
            error, self.model_error = self.model_error, None
            raise error
        tool, args = self.plan()[self.position]
        if tool == "finish":
            return Decision("finish", "sim-large", 2000, 100, 2.0, note="pull request opened")
        return Decision("tool", "sim-large", 2000, 200, 2.0, tool=tool, args=args)

    def observe(self, tool, result) -> None:
        if tool == "finish" or result is None or not result.ok:
            return  # the same call again; three identical failures stop the run (Chapter 10)
        if tool == "run_tests" and result.failure:
            self.position = len(self.plan()) - 1  # failing tests: the finish is refused, the run hands back
            return
        self.position += 1


class Deployment:
    """Everything one worker process holds, rebuilt from files in `root` (as a restarted process would)."""

    def __init__(self, root: Path, clock: Clock | None = None, code: str = GOOD_CODE) -> None:
        self.root, self.clock, self.code = root, clock or Clock(), code
        db = str(root / "relay.db")
        self.queue = AgentJobQueue(db)
        self.store = RunStore(root / "runs.db")
        self.ledger = EffectLedger(db, self.clock.stamp)
        self.registry = SharedRegistry(REGISTRY, db, clock=self.clock)
        self.tokens = TokenService(self.registry, KEY, clock=self.clock, new_id=lambda: "jti-1")
        self.trail = AuditTrail(root / "trail.jsonl", clock=self.clock.stamp)
        self.github = FakeGitHub(root / "github.json")
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.sandbox_runs: list = []
        self.on_sandbox = None  # a fault to inject while the agent's tests run
        self.policies: list[HelperScript] = []
        self.breaker = CircuitBreaker("model", self.clock, threshold=3, window_s=120, cooldown_s=60)
        self.rate_limit_until = None

    def person(self, name: str) -> dict:
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def proof(self) -> dict:
        return {"iss": GITHUB, "sub": "repo:relay-example/relay:environment:spec-to-pr",
                "aud": "relay-token-exchange", "iat": self.clock()}

    def build(self, run_id: str, run: dict):
        task_id = run["task_id"]
        files = {"src/relay/feature.py": "def add(a, b):\n    raise NotImplementedError\n"}
        policy = HelperScript(task_id, self.code, run["checkpoint"].get("policy", {}).get("position", 0))
        if self.rate_limit_until is not None and self.clock() < self.rate_limit_until:
            policy.model_error = RateLimited("model", 30.0)
        self.policies.append(policy)
        session = AgentSession(self.tokens, "spec-to-pr-helper", ["tasks:read:platform"], prove=self.proof,
                               subject=lambda: self.person(run["on_behalf_of"]))
        meter = Meter(Budget(**(run["budget"] or {"max_steps": 40, "max_usd": 0.60, "max_seconds": 600})))
        if run["checkpoint"].get("meter"):
            meter.restore(run["checkpoint"]["meter"])
        branch_file = self.root / f"branch-{task_id}.json"  # the run's branch outlives any worker process
        branch = {"files": json.loads(branch_file.read_text(encoding="utf-8")) if branch_file.exists() else files}

        def edit(args):
            branch["files"][args["path"]] = args["content"]
            branch_file.write_text(json.dumps(branch["files"]), encoding="utf-8")
            return ToolOutput("edited", 0.1, progress="diff:" + hashlib.sha256(args["content"].encode()).hexdigest())

        def sandbox_files():
            return {"feature.py": branch["files"]["src/relay/feature.py"], "tests_approved.py": APPROVED_TEST}

        handlers = {
            "read_task": lambda a: ToolOutput({"task": a["task_id"]}, 0.1),
            "read_file": lambda a: ToolOutput(branch["files"].get(a["path"], ""), 0.1, progress="read:" + a["path"]),
            "search_code": lambda a: ToolOutput([], 0.1),
            "edit_file": edit,
            "run_tests": sandboxed_tests(sandbox_files, RUNNER, SandboxPolicy(timeout_s=3),
                                         on_result=self._sandbox_result),
            "run_prcheck": lambda a: ToolOutput("0 findings", 0.1),
            "open_pull_request": ledgered_pull_request(self.ledger, run_id, task_id, self.github.open_pr),
        }
        diff = lambda: hashlib.sha256(json.dumps(branch["files"], sort_keys=True).encode()).hexdigest()  # noqa: E731
        derive = {"edit_file": lambda a: {"before_sha256": hashlib.sha256(
                      branch["files"].get(a["path"], "").encode()).hexdigest()},
                  "open_pull_request": lambda a: {"diff_sha256": diff()}}
        boundary = ToolBoundary(run_id, "spec-to-pr-helper", PRODUCTION_HELPER_TOOLS, handlers, session, meter,
                                self.store, self.trail, self.gate, frozenset({"src/relay/feature.py"}),
                                self.clock.stamp, derive=derive)
        return policy, boundary, StopRules(), lambda: bool(self.github.prs)

    def _sandbox_result(self, result) -> None:
        self.sandbox_runs.append(result)
        if self.on_sandbox is not None:
            self.on_sandbox(result)

    def worker(self, worker_id: str = "w1", tracer=None) -> AgentWorker:
        kind = AgentKind("model", lambda ctx: run_agent(ctx, self.store, self.build, self.clock.stamp))
        return AgentWorker(self.queue, {"spec-to-pr": kind}, worker_id, self.clock, {"model": self.breaker},
                           lease_s=120.0, tracer=tracer)

    def enqueue(self, task_id: str = "RLY-2301", person: str = "priya.n", traceparent: str | None = None):
        return self.queue.enqueue("spec-to-pr", task_id, {"task_id": task_id, "agent_id": "spec-to-pr-helper",
                                                          "on_behalf_of": person}, self.clock(),
                                  traceparent=traceparent)

    def approve_pending(self, person: str = "priya.n") -> int:
        rows = self.store.conn.execute("SELECT approval_id FROM agent_approvals WHERE status = 'pending'").fetchall()
        for row in rows:  # the decision wakes the parked job (decide_and_wake), as the approval route would
            decide_and_wake(self.gate, self.queue, row["approval_id"], self.person(person), True, "diff read",
                            self.clock())
        return len(rows)
