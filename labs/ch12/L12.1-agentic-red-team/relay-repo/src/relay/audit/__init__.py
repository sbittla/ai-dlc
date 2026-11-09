"""Agent identity, audit trail, redaction and kill switch (added in 4.23.0; ADR-020 to ADR-023).

Standard library only, and independent of relay.service and relay.worker: the service and the
worker will call this package (a later wiring change), never the other way round.
"""

from .identity import (AUDIENCE, FORBIDDEN_SCOPES, MAX_TTL_SECONDS, AgentIdentity, AgentRegistry, RegistryError,
                       TokenRejected, TokenService, validate)
from .killswitch import (QUARANTINE_POLICY, KillSwitchResult, RestoreRefused, quarantine_policy, restore,
                         revoke_older_sessions_policy, trip)
from .redact import redact, redact_value
from .trail import GENESIS, AuditTrail, Verification, load, record_hash, verify

__all__ = ["AUDIENCE", "FORBIDDEN_SCOPES", "MAX_TTL_SECONDS", "AgentIdentity", "AgentRegistry", "RegistryError",
           "TokenRejected", "TokenService", "validate", "QUARANTINE_POLICY", "KillSwitchResult", "RestoreRefused",
           "quarantine_policy", "restore", "revoke_older_sessions_policy", "trip", "redact", "redact_value",
           "GENESIS", "AuditTrail", "Verification", "load", "record_hash", "verify"]
