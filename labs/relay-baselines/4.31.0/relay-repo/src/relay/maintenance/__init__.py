"""Bounded autonomy for maintenance (added in 4.31.0; ADR-053 to ADR-056).

Relay's maintenance bot (`maintenance-bot` in `governance/agents.json`) works at autonomy tier T2 on narrow task
types: dependency and vulnerability updates, documentation upkeep, bug reproduction and dated table extensions.

- `reports`: reports become tasks from structured fields only; free text stays untrusted data.
- `semver` and `updates`: what a version bump claims, and updates proposed only from the mirror.
- `evidence`: reproduction, tests and checks run in Chapter 18's sandbox, labelled verified, modelled or deployed.
- `policy`: task types, tiers, protected paths (the bot cannot change itself) and who may approve.
- `proposals`: a person approves the exact diff and evidence before a pull request is opened; the bot never
  approves, merges or deploys.
- `agent_step`: the one model-driven step and its four tools, behind Chapter 10's boundary.
- `longrun`: campaigns of many items with checkpoints, budgets, cancellation and escalation, on Chapter 18's
  queue and Chapter 10's run store.
- `guard`: the guard metric a release carrying the bot's change is judged on, and the rollback it triggers.
- `autonomy`: task success, regression, rollback, intervention, violations and cost, and the T4 criteria.
- `safety_case`: a claims-arguments-evidence case checked against the results of its evidence.

Standard library and Relay's own packages only; no network module.
"""

from .autonomy import Metrics, eligibility, mcnemar_exact, metrics, runs_needed, verdict, wilson
from .evidence import Bundle, Check, Item, item, reproduce, sandbox_check
from .guard import GuardDecision, Window, judge
from .policy import CodeOwners, Policy, TaskType, approver_problem, load, load_file, validate
from .proposals import Proposal, ProposalDesk, ProposalRefused
from .reports import Report, Triage, triage
from .semver import Version, bump_kind, parse
from .updates import Mirror, UpdatePlan, plan_update

__all__ = ["Metrics", "eligibility", "mcnemar_exact", "metrics", "runs_needed", "verdict", "wilson", "Bundle",
           "Check", "Item", "item", "reproduce", "sandbox_check", "GuardDecision", "Window", "judge", "CodeOwners",
           "Policy", "TaskType", "approver_problem", "load", "load_file", "validate", "Proposal", "ProposalDesk",
           "ProposalRefused", "Report", "Triage", "triage", "Version", "bump_kind", "parse", "Mirror", "UpdatePlan",
           "plan_update"]
