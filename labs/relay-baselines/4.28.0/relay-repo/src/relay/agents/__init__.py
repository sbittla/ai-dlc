"""The runtime Relay's agents run in (added in 4.24.0; ADR-024 to ADR-027).

Budgets and stopping conditions (`budget`, `loop`), typed tool contracts and the tool-call boundary
(`contracts`, `tools`, `boundary`, `session`), durable run state with idempotent, resumable steps
(`state`), approval gates (`approval`), and compaction and reviewed long-term memory
(`memory`). Agents run under their own identities from `relay.audit`,
and every call they make is written to its audit trail.

Standard library, `relay.audit` and itself only: no network, and nothing here imports the service, the
worker or the escalation engine. A model is whatever object implements `loop.Policy`; the simulated
models and the optional live adapter live in Lab 10.1, not in Relay.
"""

from .approval import Approval, ApprovalGate, ApprovalRefused, apply_budget_raise, request_budget_raise
from .boundary import AwaitingApproval, ToolBoundary, ToolOutput, ToolResult
from .budget import DEFAULT_PRICES, PRICES_AS_OF, Budget, BudgetExceeded, Meter, Price, cost_usd
from .contracts import Param, ToolContract, args_sha256, idempotency_key, path_problem, validate_args
from .loop import Decision, LoopResult, StepRecord, StopRules, run_loop, stop_reason
from .memory import MemoryStore, Message, compact
from .session import AgentRevoked, AgentSession, DelegationExpired
from .state import RunStore
from .tools import HELPER_TOOLS, RECALL_MEMORY

__all__ = ["Approval", "ApprovalGate", "ApprovalRefused", "apply_budget_raise", "request_budget_raise",
           "AwaitingApproval", "ToolBoundary", "ToolOutput", "ToolResult", "DEFAULT_PRICES", "PRICES_AS_OF",
           "Budget", "BudgetExceeded", "Meter", "Price", "cost_usd",
           "Param", "ToolContract", "args_sha256", "idempotency_key", "path_problem", "validate_args", "Decision",
           "LoopResult", "StepRecord", "StopRules", "run_loop", "stop_reason", "AgentRevoked", "AgentSession",
           "DelegationExpired",
           "RunStore", "HELPER_TOOLS", "MemoryStore", "Message", "RECALL_MEMORY", "compact"]
