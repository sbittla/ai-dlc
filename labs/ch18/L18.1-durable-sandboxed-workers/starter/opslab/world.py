"""The spec-to-PR helper deployed as a queue worker, in simulated time (provided; not a TODO).

Everything that would be a separate process in production (a worker, the monitor, a person's console) gets
its own objects on shared files in one folder, so a "restart" rebuilds them from the files. The model is a
scripted stand-in; the queue, the ledger, the sandbox, the registry state, the boundary and the approval gate
are Relay 4.30.0's real code. Time is a simulated clock: each model call takes 2 s, each tool the seconds in
STEP_SECONDS, whatever the real sandbox took.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import LAB_ROOT  # noqa: F401  (puts relay-repo/src on the path)
from relay.agents import ApprovalGate, Budget, Decision, Meter, RunStore, StopRules, ToolBoundary, ToolOutput
from relay.agents.session import AgentSession
from relay.agentops import AgentJobQueue, CircuitBreaker, EffectLedger, SandboxPolicy, SharedRegistry
from relay.agentops.tools import PRODUCTION_HELPER_TOOLS, ledgered_pull_request, sandboxed_tests
from relay.agentops.worker import AgentKind, AgentWorker, decide_and_wake, run_agent
from relay.audit import AuditTrail, TokenService

PERSON_ISSUER = "https://login.relay.example"
GITHUB = "https://token.actions.githubusercontent.com"
T0 = 1_805_101_200.0  # Monday 2027-03-15 09:00:00 UTC
STEP_SECONDS = {"read_task": 1, "read_file": 1, "search_code": 1, "edit_file": 1, "run_tests": 100,
                "run_prcheck": 5, "open_pull_request": 2}
REGISTRY = {
    "version": "lab", "people": ["priya.n", "sam.o", "aisha.r", "tomas.b"], "person_issuer": PERSON_ISSUER,
    "agents": [{"agent_id": "spec-to-pr-helper", "kind": "ci-job", "owner": "sam.o", "issuer": GITHUB,
                "subject": "repo:relay-example/relay:environment:spec-to-pr", "cloud_role": None,
                "scopes": ["tasks:read:platform"], "max_ttl_seconds": 900, "delegation": "required",
                "delegators": ["priya.n", "sam.o"], "github_app": "relay-spec-to-pr"}],
}
RUNNER = "import tests_approved\nraise SystemExit(tests_approved.main())\n"
GOOD_CODE = "def add(a, b):\n    return a + b\n"
APPROVED_TEST = ("from feature import add\n\n\ndef main():\n    assert add(2, 3) == 5\n    print('1 passed')\n"
                 "    return 0\n")
ESCAPING_CODE = ("import os, socket\ntry:\n    os.system('echo planted')\nexcept PermissionError:\n    pass\n"
                 "try:\n    socket.create_connection(('169.254.169.254', 80), 1)\nexcept PermissionError:\n    pass\n"
                 "def add(a, b):\n    return a + b\n")
KEY = hashlib.sha256(b"lab 18.1 token key (not a secret)").digest()


class Clock:
    def __init__(self, t: float = T0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def stamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Crash(BaseException):
    """The worker process dies here; nothing in the worker catches a BaseException."""


class CodeHost:
    """A code host that keeps one pull request per key and looks before it creates. It can die once after creating."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            path.write_text(json.dumps({"prs": [], "creates": 0}), encoding="utf-8")
        self.crash_after_create = False

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def creates(self) -> int:
        return self._load()["creates"]

    def open_pr(self, key: str, args: dict) -> dict:
        data = self._load()
        found = [p for p in data["prs"] if p["key"] == key]
        if found:
            return {"number": found[0]["number"], "existing": True}
        number = 5100 + len(data["prs"])
        data["prs"].append({"key": key, "number": number})
        data["creates"] += 1
        self.path.write_text(json.dumps(data), encoding="utf-8")
        if self.crash_after_create:
            self.crash_after_create = False
            raise Crash("the worker died after the code host created the pull request")
        return {"number": number, "existing": False}


class Script:
    """The scripted model: read, edit, test, open a pull request, finish; hand back if the tests fail."""

    actor = "spec-to-pr-helper"

    def __init__(self, world: World, task_id: str, code: str, position: int = 0) -> None:
        self.world, self.task_id, self.code, self.position = world, task_id, code, position
        self.fault = None

    def plan(self) -> list:
        return [("read_task", {"task_id": self.task_id}), ("read_file", {"path": "src/relay/feature.py"}),
                ("edit_file", {"path": "src/relay/feature.py", "content": self.code}),
                ("run_tests", {"target": "approved"}),
                ("open_pull_request", {"branch": f"agent/{self.task_id}", "title": self.task_id,
                                       "body": "Claims: add() returns the sum (src/relay/feature.py:2)."}),
                ("finish", {})]

    def state(self) -> dict:
        return {"position": self.position}

    def next_call(self):
        return "sim-large", 2000, 512, 0

    def decide(self) -> Decision:
        self.world.clock.t += 2
        if self.fault is not None:
            fault, self.fault = self.fault, None
            raise fault
        if self.position < 0:
            return Decision("hand_back", "sim-large", 2000, 60, 2.0, note="tests_failed")
        tool, args = self.plan()[self.position]
        if tool == "finish":
            return Decision("finish", "sim-large", 2000, 80, 2.0, note="pull request opened")
        return Decision("tool", "sim-large", 2000, 200, 2.0, tool=tool, args=args)

    def observe(self, tool, result) -> None:
        if tool == "finish" or result is None or not result.ok:
            return
        if tool == "run_tests" and result.failure:
            self.position = -1
            return
        self.position += 1


class World:
    """One worker process's objects, on the shared files in `root`."""

    def __init__(self, root: Path, clock: Clock | None = None, code: str = GOOD_CODE, lease_s: float = 120.0,
                 tracer=None) -> None:
        self.root, self.clock, self.code, self.lease_s, self.tracer = Path(root), clock or Clock(), code, lease_s, tracer
        db = str(self.root / "relay.db")
        self.queue = AgentJobQueue(db)
        self.store = RunStore(self.root / "runs.db")
        self.ledger = EffectLedger(db, self.clock.stamp)
        self.registry = SharedRegistry(REGISTRY, db, clock=self.clock)
        self.tokens = TokenService(self.registry, KEY, clock=self.clock)
        self.trail = AuditTrail(self.root / "trail.jsonl", clock=self.clock.stamp)
        self.host = CodeHost(self.root / "codehost.json")
        self.gate = ApprovalGate(self.store, self.trail, self.registry.people, self.clock, self.clock.stamp,
                                 PERSON_ISSUER)
        self.breaker = CircuitBreaker("model", self.clock, threshold=3, window_s=120, cooldown_s=60)
        self.sandbox_results: list = []
        self.on_sandbox = None
        self.model_fault = None  # a function of the clock returning an exception to raise, or None

    def person(self, name: str) -> dict:
        return {"iss": PERSON_ISSUER, "sub": name, "aud": "relay-token-exchange", "iat": self.clock()}

    def proof(self) -> dict:
        return {"iss": GITHUB, "sub": "repo:relay-example/relay:environment:spec-to-pr",
                "aud": "relay-token-exchange", "iat": self.clock()}

    def _timed(self, tool: str, handler):
        def run(args):
            out = handler(args)
            self.clock.t += STEP_SECONDS[tool]
            return out
        return run

    def _sandbox_result(self, result) -> None:
        self.sandbox_results.append(result)
        if self.on_sandbox is not None:
            self.on_sandbox(result)

    def build(self, run_id: str, run: dict):
        task_id = run["task_id"]
        policy = Script(self, task_id, self.code, run["checkpoint"].get("policy", {}).get("position", 0))
        if self.model_fault is not None:
            policy.fault = self.model_fault(self.clock())
        session = AgentSession(self.tokens, "spec-to-pr-helper", ["tasks:read:platform"], prove=self.proof,
                               subject=lambda: self.person(run["on_behalf_of"]))
        meter = Meter(Budget(**(run["budget"] or {"max_steps": 40, "max_usd": 0.60, "max_seconds": 900})))
        if run["checkpoint"].get("meter"):
            meter.restore(run["checkpoint"]["meter"])
        branch_file = self.root / f"branch-{task_id}.json"
        start = {"src/relay/feature.py": "def add(a, b):\n    raise NotImplementedError\n"}
        branch = json.loads(branch_file.read_text(encoding="utf-8")) if branch_file.exists() else start

        def edit(args):
            branch[args["path"]] = args["content"]
            branch_file.write_text(json.dumps(branch), encoding="utf-8")
            return ToolOutput("edited", 1.0, progress="diff:" + hashlib.sha256(args["content"].encode()).hexdigest())

        def tests_files():
            return {"feature.py": branch["src/relay/feature.py"], "tests_approved.py": APPROVED_TEST}

        handlers = {
            "read_task": lambda a: ToolOutput({"task": a["task_id"]}, 1.0),
            "read_file": lambda a: ToolOutput(branch.get(a["path"], ""), 1.0, progress="read:" + a["path"]),
            "search_code": lambda a: ToolOutput([], 1.0),
            "edit_file": edit,
            "run_tests": sandboxed_tests(tests_files, RUNNER, SandboxPolicy(timeout_s=10),
                                         on_result=self._sandbox_result),
            "run_prcheck": lambda a: ToolOutput("0 findings", 5.0),
            "open_pull_request": ledgered_pull_request(self.ledger, run_id, task_id, self.host.open_pr),
        }
        handlers = {name: self._timed(name, h) for name, h in handlers.items()}
        diff = lambda: hashlib.sha256(json.dumps(branch, sort_keys=True).encode()).hexdigest()  # noqa: E731
        derive = {"edit_file": lambda a: {"before_sha256": hashlib.sha256(branch.get(a["path"], "").encode())
                                          .hexdigest()},
                  "open_pull_request": lambda a: {"diff_sha256": diff()}}
        boundary = ToolBoundary(run_id, "spec-to-pr-helper", PRODUCTION_HELPER_TOOLS, handlers, session, meter,
                                self.store, self.trail, self.gate, frozenset({"src/relay/feature.py"}),
                                self.clock.stamp, derive=derive)
        return policy, boundary, StopRules(), lambda: self.host.creates > 0 and any(
            p["key"] == f"pr:{task_id}" for p in self.host._load()["prs"])

    def worker(self, worker_id: str = "worker-1") -> AgentWorker:
        kind = AgentKind("model", lambda ctx: run_agent(ctx, self.store, self.build, self.clock.stamp))
        return AgentWorker(self.queue, {"spec-to-pr": kind}, worker_id, self.clock, {"model": self.breaker},
                           lease_s=self.lease_s, tracer=self.tracer)

    def enqueue(self, task_id: str = "RLY-2301", person: str = "priya.n", traceparent: str | None = None,
                payload: dict | None = None):
        body = payload if payload is not None else {"task_id": task_id, "agent_id": "spec-to-pr-helper",
                                                    "on_behalf_of": person}
        return self.queue.enqueue("spec-to-pr", task_id, body, self.clock(), traceparent=traceparent)

    def approve_and_wake(self, person: str = "priya.n") -> int:
        """The requester approves every pending request with a fresh proof; each decision wakes its job."""
        rows = self.store.conn.execute("SELECT approval_id FROM agent_approvals WHERE status = 'pending' "
                                       "ORDER BY approval_id").fetchall()
        for row in rows:
            decide_and_wake(self.gate, self.queue, row["approval_id"], self.person(person), True,
                            "diff and tests read", self.clock())
        return len(rows)
