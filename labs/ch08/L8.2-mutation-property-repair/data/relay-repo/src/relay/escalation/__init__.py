"""Escalation rules: the engine, built test-first from the spec (Relay 4.20.0).

Specification: specs/001-escalation-rules/spec.md (ESC-SPEC-1), version below.
Contract: specs/001-escalation-rules/contracts/escalation-rules.schema.json.
HTTP routes: relay.service (ADR-009), described by contracts/escalation-api.openapi.json.

Pure parts: validate_rule, evaluate, business hours (hours) and message
rendering (delivery). Stateful parts: the store and the engine's functions,
which take an explicit time and send nothing; delivery adapters read the outbox.
"""

SPEC_ID = "ESC-SPEC-1"
SPEC_VERSION = "1.1.0"

from .contract import rule_from_document, to_document, to_rule_document, validate  # noqa: E402
from .engine import (EngineConfig, PassResult, RuleIdInUse, Webhook, acknowledge, escalation_view,  # noqa: E402
                     record_suggestion, refuse, rules_for, run_pass, save_rule, set_priority)
from .evaluate import evaluate  # noqa: E402
from .hours import add_business_minutes  # noqa: E402
from .model import (BusinessHours, EmailMessage, EscalationState, Evaluation, Rejection, Rule,  # noqa: E402
                    RuleRejected, Step, StepDecision, WebhookEvent)
from .rules import validate_rule  # noqa: E402
from .store import EscalationStore  # noqa: E402

__all__ = ["SPEC_ID", "SPEC_VERSION", "BusinessHours", "EmailMessage", "EngineConfig", "EscalationState",
           "EscalationStore", "Evaluation", "PassResult", "Rejection", "Rule", "RuleIdInUse", "RuleRejected", "Step",
           "StepDecision", "Webhook", "WebhookEvent", "acknowledge", "add_business_minutes", "escalation_view",
           "evaluate", "record_suggestion", "refuse", "rule_from_document", "rules_for", "run_pass", "save_rule",
           "set_priority", "to_document", "to_rule_document", "validate", "validate_rule"]
