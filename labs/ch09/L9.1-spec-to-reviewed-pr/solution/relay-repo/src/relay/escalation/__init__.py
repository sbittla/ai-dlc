"""Escalation rules: the engine, built test-first from the spec (Relay 4.20.0; rule deletion in 4.22.0).

Specification: specs/001-escalation-rules/spec.md (ESC-SPEC-1), version below.
Contract: specs/001-escalation-rules/contracts/escalation-rules.schema.json.
HTTP routes: relay.service (ADR-009), described by contracts/escalation-api.openapi.json.

Pure parts: validate_rule, evaluate, business hours (hours) and message
rendering (delivery). Stateful parts: the store, its schema migrations and the
engine's functions, which take an explicit time and send nothing; delivery
adapters read the outbox. The worker runs `run_pass` on each loop (ADR-017).
"""

SPEC_ID = "ESC-SPEC-1"
SPEC_VERSION = "1.2.0"

from .contract import rule_from_document, to_document, to_rule_document, validate  # noqa: E402
from .engine import (EngineConfig, PassResult, RuleIdInUse, RuleNotFound, Webhook, acknowledge,  # noqa: E402
                     delete_rule, escalation_view, notice_recipients, record_suggestion, refuse, rules_for,
                     run_pass, save_rule, set_priority)
from .evaluate import evaluate  # noqa: E402
from .hours import add_business_minutes  # noqa: E402
from .migrations import MigrationRefused  # noqa: E402
from .model import (BusinessHours, EmailMessage, EscalationState, Evaluation, Rejection, Rule,  # noqa: E402
                    RuleDeleted, RuleRejected, Step, StepDecision, WebhookEvent)
from .rules import validate_rule  # noqa: E402
from .store import EscalationStore  # noqa: E402

__all__ = ["SPEC_ID", "SPEC_VERSION", "BusinessHours", "EmailMessage", "EngineConfig", "EscalationState",
           "EscalationStore", "Evaluation", "MigrationRefused", "PassResult", "Rejection", "Rule", "RuleDeleted",
           "RuleIdInUse", "RuleNotFound", "RuleRejected", "Step", "StepDecision", "Webhook", "WebhookEvent",
           "acknowledge", "add_business_minutes", "delete_rule", "escalation_view", "evaluate",
           "notice_recipients", "record_suggestion", "refuse", "rule_from_document", "rules_for", "run_pass",
           "save_rule", "set_priority", "to_document", "to_rule_document", "validate", "validate_rule"]
