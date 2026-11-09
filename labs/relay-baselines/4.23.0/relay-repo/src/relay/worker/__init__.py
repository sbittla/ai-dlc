"""Relay's background worker: triage (added in 4.19.0; ADR-007) and escalation passes (4.22.0; ADR-017).

This package's public interface is what this file exports. Other Relay
modules, including `relay.service`, import from `relay.worker` only, never
from its submodules; `tests/test_architecture.py` enforces that.

    python -m relay.worker --db relay.db           # run until stopped
    python -m relay.worker --db relay.db --drain   # process what is queued, then exit
"""

from .escalation import EscalationPasses
from .queue import IdempotencyConflict, Job, TriageQueue
from .runner import STALL_AFTER_S, Worker, is_stalled

__all__ = ["EscalationPasses", "IdempotencyConflict", "Job", "TriageQueue", "STALL_AFTER_S", "Worker", "is_stalled"]
