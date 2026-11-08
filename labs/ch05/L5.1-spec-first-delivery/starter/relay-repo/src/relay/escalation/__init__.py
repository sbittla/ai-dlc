"""Escalation rules: the spec-first slice (rule validation and evaluation only).

Specification: specs/001-escalation-rules/spec.md (ESC-SPEC-1), version below.
Contract: specs/001-escalation-rules/contracts/escalation-rules.schema.json.
Not here yet: storage, notification delivery, audit, business hours and the
flood cap. Chapter 8 builds the full engine test-first from the same spec.
"""

SPEC_ID = "ESC-SPEC-1"
SPEC_VERSION = "1.0.0"

from .contract import to_document, validate  # noqa: E402
from .evaluate import evaluate  # noqa: E402
from .model import EscalationState, Evaluation, Rejection, Rule, RuleRejected, Step, StepDecision  # noqa: E402
from .rules import validate_rule  # noqa: E402

__all__ = ["SPEC_ID", "SPEC_VERSION", "EscalationState", "Evaluation", "Rejection", "Rule", "RuleRejected",
           "Step", "StepDecision", "evaluate", "to_document", "validate", "validate_rule"]
