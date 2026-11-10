"""Running Relay's agents in production (added in 4.30.0; ADR-049 to ADR-052).

- `jobs`: a durable agent job queue with business-key deduplication, fenced leases, a dead-letter state,
  cancellation and approval waits.
- `effects`: the effect ledger, so an external effect happens at most once per business key across runs.
- `resilience`: failure classes, Retry-After, and a circuit breaker per dependency.
- `worker`: agent runs as queue workers on Chapter 10's runtime, with heartbeats, breakers and traces.
- `sandbox` and `sandbox_child`: agent-written code in a separate, locked-down process.
- `tools`: production contracts and handlers (sandboxed `run_tests`, `run_code`, the ledgered pull request).
- `registry_state`: the agent registry's enabled flags and epochs in the shared database.
- `gateway`: agent tokens verified, and agent requests audited, at the HTTP service.

Standard library and Relay's own packages only. Nothing here imports a network module: the sandbox starts a
process, and the gateway is WSGI middleware.
"""

from .effects import EffectConflict, EffectLedger, UnknownEffectOutcome
from .jobs import AgentJob, AgentJobQueue, JobCancelled, JobConflict, LeaseLost, backoff_s, retry_delay_s
from .registry_state import SharedRegistry
from .resilience import (CircuitBreaker, DependencyError, DependencyTimeout, PoisonPayload, RateLimited,
                         parse_retry_after)
from .sandbox import SandboxPolicy, SandboxResult, run_code

__all__ = ["EffectConflict", "EffectLedger", "UnknownEffectOutcome", "AgentJob", "AgentJobQueue", "JobCancelled",
           "JobConflict", "LeaseLost", "backoff_s", "retry_delay_s", "SharedRegistry", "CircuitBreaker",
           "DependencyError", "DependencyTimeout", "PoisonPayload", "RateLimited", "parse_retry_after",
           "SandboxPolicy", "SandboxResult", "run_code"]
