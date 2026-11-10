"""The tool-call boundary: every check between a model's request and its effect (added in 4.24.0; ADR-025).

Chapter 2's Listing 2.4 sketched the shape: an allowlist, argument validation, a permission check and an
audit record. This is the complete version Relay's agents run behind. For each call, in this order:

  1. unknown_tool       the tool is not in this agent's allowlist
  2. invalid_args       the arguments break the contract (types, lengths, choices, paths, the task's files)
  2b. tainted_external  from 4.26.0 (ADR-034): once the run has read untrusted text (a contract with
                        `untrusted_result`), an external effect without an approval rule is refused
  3. token              the agent's own token is verified for the contract's scope, with no cache;
                        a disabled or revoked agent is refused and AgentRevoked ends the run
  4. budget             the meter refuses another step once a limit is reached (BudgetExceeded)
  5. derived            arguments the model may not set (a diff's hash, a file's prior hash) are computed
                        here from the real state; anything the model sent for them is discarded
  6. approval           a gated call waits for a person's approval of these exact arguments
  7. journal            a non-read call with a key already recorded returns the recorded result
  8. execute            the handler runs; its result is cut to the contract's size, and paths no agent
                        may read are removed from a list of paths
  9. record             the step's outcome goes to the journal and the audit trail

The taint is a property of the run, not of one call: it is read back from the run's journal when a
boundary is built, so a resumed run is still tainted. The journal keeps its own taint record (tool `TAINT_STEP`),
independent of contract names, so a run resumed with a different tool set stays tainted too. A call to an
untrusted tool taints the run whatever its outcome, including an error, because an error message can carry
the outsider's text. Taint does not cross runs or agents: a run that receives another run's output must mark
that tool's result untrusted itself. An approval requested by a tainted run says so in
its audit record, so the person deciding knows the request may have been steered.

Every call that reaches the boundary leaves an audit record, refusals included, and that includes the
refusals that end the run (revoked, budget). Records carry the agent, its accountable owner, the person it
acts for and its token's ID. Arguments are recorded by hash, never in full, and results never.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..audit import AuditTrail, TokenRejected
from .approval import ApprovalGate
from .budget import BudgetExceeded, Meter
from .contracts import ToolContract, args_sha256, idempotency_key, path_problem, validate_args
from .session import AgentRevoked, AgentSession
from .state import RunStore


TAINT_STEP = "run.taint"  # the journal record that marks a run tainted (ADR-034)


@dataclass(frozen=True)
class ToolOutput:
    """What a handler returns: the value for the model, the time it took, and what it means for stopping.

    `failure` is a stable signature such as "tests:tests/test_f11.py" when the call shows a problem the run
    must fix; repeated signatures stop the run (`loop.stop_reason`). `progress` is a key for the state the
    call observed, such as a diff's hash; a run whose steps stop producing new keys has stalled.
    """

    value: object
    seconds: float = 0.0
    failure: str | None = None
    progress: str | None = None


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    value: object = None
    code: str | None = None          # refusal or error code when not ok
    approval_id: str | None = None
    replayed: bool = False
    truncated: bool = False
    failure: str | None = None
    progress: str | None = None


class AwaitingApproval(Exception):
    def __init__(self, approval_id: str) -> None:
        super().__init__(approval_id)
        self.approval_id = approval_id


@dataclass
class ToolBoundary:
    run_id: str
    agent_id: str
    contracts: dict[str, ToolContract]
    handlers: dict[str, Callable[[dict], ToolOutput]]
    session: AgentSession
    meter: Meter
    store: RunStore
    trail: AuditTrail
    gate: ApprovalGate
    write_paths: frozenset[str]
    stamp: Callable[[], str]
    derive: dict[str, Callable[[dict], dict]] = field(default_factory=dict)
    refusals: dict[str, int] = field(default_factory=dict)
    tainted: bool = False

    def __post_init__(self) -> None:
        untrusted = {name for name, c in self.contracts.items() if c.untrusted_result}
        steps = self.store.steps(self.run_id)
        if any(s["tool"] == TAINT_STEP or (s["tool"] in untrusted and s["outcome"] in ("ok", "replayed", "error"))
               for s in steps):
            self.tainted = True

    def _taint(self, tool: str) -> None:
        """Mark the run tainted, once, with a journal record that does not depend on contract names."""
        if self.tainted:
            return
        self.tainted = True
        self.store.note_step(self.run_id, self.agent_id, TAINT_STEP, "-", "ok", {"after": tool}, self.stamp())

    def _audit(self, tool: str, outcome: str, args_sha: str, code: str | None = None, extra: dict | None = None):
        claims = self.session.claims or {}
        detail = {"tool": tool, "args_sha256": args_sha}
        if code:
            detail["code"] = code
        detail.update(extra or {})
        self.trail.append(agent_id=self.agent_id, owner=claims.get("own"), on_behalf_of=claims.get("obo"),
                          credential=claims.get("jti"), action=f"tool.{tool}", resource=f"run:{self.run_id}",
                          outcome=outcome, source="relay.agents", at=self.stamp(), detail=detail)

    def _refuse(self, tool: str, args: dict, code: str, detail: str = "") -> ToolResult:
        sha = args_sha256(args) if isinstance(args, dict) else "-"
        self.refusals[code] = self.refusals.get(code, 0) + 1
        self.store.note_step(self.run_id, self.agent_id, tool, sha, "refused", {"code": code, "detail": detail},
                             self.stamp())
        self._audit(tool, "refused", sha, code)
        return ToolResult(False, detail, code, failure=f"refused:{code}")

    def call(self, tool: str, args: dict) -> ToolResult:
        contract = self.contracts.get(tool)
        if contract is None or tool not in self.handlers:
            return self._refuse(tool, args, "unknown_tool", f"{tool} is not one of this agent's tools")
        if isinstance(args, dict) and contract.derived:
            args = {k: v for k, v in args.items() if k not in contract.derived}
        problems = validate_args(contract, args, self.write_paths)
        if problems:
            path_words = ("path must", "never readable", "file list")
            code = "path_not_allowed" if any(w in p for p in problems for w in path_words) else "invalid_args"
            return self._refuse(tool, args, code, "; ".join(problems))
        if self.tainted and contract.effect == "external" and contract.approval is None:
            return self._refuse(tool, args, "tainted_external",
                                "this run has read untrusted text; an external effect needs a person's approval")
        try:
            self.session.verify(contract.scope)
        except AgentRevoked as exc:  # recorded, then the run ends
            self._refuse(tool, args, f"{exc.status}:{exc.code}")
            raise
        except TokenRejected as exc:  # scope_missing: the agent asked for something its token does not hold
            return self._refuse(tool, args, exc.code)
        try:
            self.meter.check()
        except BudgetExceeded as exc:
            self._refuse(tool, args, f"budget:{exc.kind}")
            raise
        if contract.derived:
            provider = self.derive.get(tool)
            if provider is None:
                return self._refuse(tool, args, "underivable", "no provider for the tool's derived arguments")
            args = {**args, **provider(args)}
        sha = args_sha256(args)
        if contract.approval is not None:
            approval = self.gate.find(self.run_id, tool, args)
            if approval is None or approval.status == "expired":
                if self.tainted:
                    self._audit(tool, "approval_requested_after_untrusted_read", sha)
                approval = self.gate.request(self.run_id, tool, args, contract.approval, self.agent_id,
                                             self.session.on_behalf_of,
                                             bound={k: args[k] for k in contract.derived})
            if approval.status == "pending":
                raise AwaitingApproval(approval.approval_id)
            if approval.status == "denied":
                return self._refuse(tool, args, "approval_denied")
        key = idempotency_key(self.run_id, contract, args)
        seq, existing = self.store.begin_step(self.run_id, key, self.agent_id, tool, sha, self.stamp())
        if existing is not None:
            outcome = existing["outcome"]
            if outcome == "ok" or (outcome == "error" and not contract.idempotent):
                self.meter.charge_tool(self.agent_id, 0.0)
                self._audit(tool, "replayed", sha, extra={"seq": seq})
                value = existing["result"]
                return ToolResult(outcome == "ok", value.get("value"), value.get("code"), replayed=True,
                                  failure=value.get("failure"), progress=value.get("progress"))
            if not contract.idempotent:  # started before a crash: outcome unknown
                return self._refuse(tool, args, "unknown_outcome",
                                    "the step may already have happened; a person checks")
            if outcome == "error":
                self.store.retry_step(self.run_id, seq)
        try:
            out = self.handlers[tool](args)
        except Exception as exc:  # a failed tool is an outcome the agent sees, not a crash of the run
            if contract.untrusted_result:
                self._taint(tool)
            self.meter.charge_tool(self.agent_id, 0.0)
            self.store.finish_step(self.run_id, seq, "error", {"code": type(exc).__name__, "value": str(exc)[:200],
                                                               "failure": f"error:{tool}"})
            self._audit(tool, "error", sha, type(exc).__name__)
            return ToolResult(False, str(exc)[:200], type(exc).__name__, failure=f"error:{tool}")
        value, removed = out.value, 0
        if contract.returns_paths and isinstance(value, list):
            kept = [v for v in value if not (isinstance(v, str) and path_problem(v))]
            removed, value = len(value) - len(kept), kept
        truncated = isinstance(value, str) and len(value) > contract.max_result_chars
        if truncated:
            value = value[: contract.max_result_chars]
        self.meter.charge_tool(self.agent_id, out.seconds)
        self.store.finish_step(self.run_id, seq, "ok", {"value": value, "failure": out.failure,
                                                        "progress": out.progress})
        if contract.untrusted_result:
            self._taint(tool)
        self._audit(tool, "ok", sha, extra={"seq": seq, "truncated": truncated, "removed_paths": removed,
                                            **({"tainted": True} if self.tainted else {})})
        return ToolResult(True, value, truncated=truncated, failure=out.failure, progress=out.progress)
