"""Approval gates for high-impact agent actions (added in 4.24.0; ADR-026).

A contract with `approval` set cannot run until a person approves that exact call. The gate records a
request, and the run waits (`awaiting_approval`) with its state saved. A person decides; the run is
resumed; the boundary finds the approval and lets the call through.

The rules, each enforced here rather than left to the agent:

- The decider is authenticated, not asserted (Chapter 14). `decide` takes the person's own short-lived
  proof, issued by the registry's `person_issuer` for Relay's audience and under five minutes old, and
  the decider is the proof's subject. An agent identity can never approve anything.
- `requester`: only the person the run acts for may approve (opening a draft pull request in their name).
  `another_person`: only someone other than that person may (raising the run's budget). A request with no
  recorded requester cannot be decided under `another_person`.
- An approval is bound to the call's exact arguments (their SHA-256), including the arguments the
  boundary derives from the real state, such as the diff's hash. If the change differs from the one the
  person saw, the old approval does not cover it.
- An approval expires (24 hours by default). An expired request can be asked again, as a new request.

What the gate does not decide: who reviews the pull request. The requester approved the diff the helper
produced; Chapter 9's PR10 counts an agent's commits as the person who ran it, so the requester cannot
also be the pull request's independent reviewer.

Every request and decision is written to the audit trail of agent actions (ADR-021).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from ..audit import AUDIENCE, AuditTrail
from ..audit import identity as _identity
from .contracts import args_sha256
from .state import RunStore

DEFAULT_TTL_SECONDS = 24 * 3600


class ApprovalRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Approval:
    approval_id: str
    run_id: str
    tool: str
    args_sha256: str
    approver_rule: str
    requested_by: str
    requested_for: str | None
    status: str
    decided_by: str | None
    reason: str | None
    expires_at: float


class ApprovalGate:
    def __init__(self, store: RunStore, trail: AuditTrail, people: frozenset[str],
                 clock: Callable[[], float], stamp: Callable[[], str], person_issuer: str,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.store = store
        self.trail = trail
        self.people = people
        self.clock = clock
        self.stamp = stamp
        self.person_issuer = person_issuer
        self.ttl_seconds = ttl_seconds

    def _row(self, approval_id: str) -> Approval:
        row = self.store.conn.execute("SELECT * FROM agent_approvals WHERE approval_id = ?",
                                      (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        d = dict(row)
        return Approval(d["approval_id"], d["run_id"], d["tool"], d["args_sha256"], d["approver_rule"],
                        d["requested_by"], d["requested_for"], d["status"], d["decided_by"], d["reason"],
                        d["expires_at"])

    def find(self, run_id: str, tool: str, args: dict) -> Approval | None:
        row = self.store.conn.execute(
            "SELECT approval_id FROM agent_approvals WHERE run_id = ? AND tool = ? AND args_sha256 = ?",
            (run_id, tool, args_sha256(args))).fetchone()
        if row is None:
            return None
        approval = self._row(row["approval_id"])
        if approval.status == "pending" and self.clock() >= approval.expires_at:
            self._set(approval.approval_id, "expired", None, "not decided before it expired")
            approval = self._row(approval.approval_id)
        return approval

    def request(self, run_id: str, tool: str, args: dict, approver_rule: str, agent_id: str,
                requested_for: str | None, bound: dict | None = None) -> Approval:
        """Record a request for this exact call, or return the one already recorded for it.

        `bound` names the derived values the approval covers (such as the diff's hash), so the audit trail
        alone can show which change a person approved.
        """
        existing = self.find(run_id, tool, args)
        sha = args_sha256(args)
        if existing is not None and existing.status == "expired":  # ask again: a new request for the same call
            with self.store._tx() as c:
                c.execute("UPDATE agent_approvals SET status = 'pending', decided_by = NULL, decided_at = NULL,"
                          " reason = NULL, requested_at = ?, expires_at = ? WHERE approval_id = ?",
                          (self.stamp(), self.clock() + self.ttl_seconds, existing.approval_id))
            self._audit_request(run_id, tool, sha, existing.approval_id, agent_id, requested_for, bound)
            return self._row(existing.approval_id)
        if existing is not None:
            return existing
        approval_id = "apv-" + hashlib.sha256(f"{run_id}|{tool}|{sha}".encode()).hexdigest()[:16]
        with self.store._tx() as c:
            c.execute("INSERT INTO agent_approvals (approval_id, run_id, tool, args_sha256, approver_rule,"
                      " requested_by, requested_for, status, requested_at, expires_at)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                      (approval_id, run_id, tool, sha, approver_rule, agent_id, requested_for, self.stamp(),
                       self.clock() + self.ttl_seconds))
        self._audit_request(run_id, tool, sha, approval_id, agent_id, requested_for, bound)
        return self._row(approval_id)

    def _audit_request(self, run_id: str, tool: str, sha: str, approval_id: str, agent_id: str,
                       requested_for: str | None, bound: dict | None) -> None:
        detail = {"tool": tool, "args_sha256": sha, "approval_id": approval_id}
        if bound:
            detail["bound"] = dict(bound)
        self.trail.append(agent_id=agent_id, owner=None, on_behalf_of=requested_for, action="approval.request",
                          resource=f"run:{run_id}", outcome="pending", source="relay.agents", at=self.stamp(),
                          detail=detail)

    def authenticate(self, proof: dict) -> str:
        """The person a proof names, if it is valid now; otherwise ApprovalRefused.

        `proof` holds claims a verifier has already checked, as in Chapter 14's token exchange: the issuer
        must be the registry's person issuer, the audience Relay's, and `iat` at most five minutes old.
        """
        iat = proof.get("iat")
        fresh = isinstance(iat, (int, float)) and -60 <= self.clock() - iat <= _identity.MAX_PROOF_AGE_SECONDS
        if proof.get("iss") != self.person_issuer or proof.get("aud") != AUDIENCE or not fresh:
            raise ApprovalRefused("bad_person_proof")
        person = proof.get("sub")
        if person not in self.people:
            raise ApprovalRefused("not_a_person")
        return person

    def decide(self, approval_id: str, proof: dict, approve: bool, reason: str) -> Approval:
        """Approve or deny, as the person `proof` authenticates.

        Refusals, in check order: bad_person_proof, not_a_person, not_the_requester, requester_unknown,
        requester_may_not_approve, expired, not_pending.
        """
        approval = self._row(approval_id)
        person = self.authenticate(proof)
        if approval.approver_rule == "requester" and person != approval.requested_for:
            raise ApprovalRefused("not_the_requester")
        if approval.approver_rule == "another_person":
            if approval.requested_for is None:
                raise ApprovalRefused("requester_unknown")
            if person == approval.requested_for:
                raise ApprovalRefused("requester_may_not_approve")
        if approval.status == "pending" and self.clock() >= approval.expires_at:
            self._set(approval_id, "expired", None, "not decided before it expired")
            raise ApprovalRefused("expired")
        if approval.status != "pending":
            raise ApprovalRefused("not_pending")
        status = "approved" if approve else "denied"
        self._set(approval_id, status, person, reason)
        self.trail.append(agent_id=approval.requested_by, owner=None, on_behalf_of=approval.requested_for,
                          action="approval.decide", resource=f"run:{approval.run_id}", outcome=status,
                          source="relay.agents", at=self.stamp(),
                          detail={"tool": approval.tool, "approval_id": approval_id, "decided_by": person})
        return self._row(approval_id)

    def _set(self, approval_id: str, status: str, person: str | None, reason: str | None) -> None:
        with self.store._tx() as c:
            c.execute("UPDATE agent_approvals SET status = ?, decided_by = ?, decided_at = ?, reason = ?"
                      " WHERE approval_id = ?", (status, person, self.stamp(), reason, approval_id))


def request_budget_raise(gate: ApprovalGate, run_id: str, new_budget: dict, agent_id: str,
                         requested_for: str | None) -> Approval:
    """Ask for a run's budget to be raised to `new_budget`. Only someone other than the requester may approve."""
    return gate.request(run_id, "raise_budget", new_budget, "another_person", agent_id, requested_for)


def apply_budget_raise(gate: ApprovalGate, run_id: str, new_budget: dict) -> dict:
    """Store `new_budget` as the run's budget, if exactly that raise was approved. Resuming reads it from the run."""
    approval = gate.find(run_id, "raise_budget", new_budget)
    if approval is None or approval.status != "approved":
        raise ApprovalRefused("not_approved")
    gate.store.set_budget(run_id, new_budget, gate.stamp())
    gate.trail.append(agent_id=approval.requested_by, owner=None, on_behalf_of=approval.requested_for,
                      action="budget.raise", resource=f"run:{run_id}", outcome="ok", source="relay.agents",
                      at=gate.stamp(), detail={"approval_id": approval.approval_id, "decided_by": approval.decided_by,
                                               "budget": dict(new_budget)})
    return new_budget
