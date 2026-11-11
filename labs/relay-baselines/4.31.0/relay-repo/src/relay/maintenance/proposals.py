"""From evidence to a pull request that waits for a person (added in 4.31.0; ADR-053).

The bot works at autonomy tier T2: it changes code in a sandbox, and a person reviews the result before it
leaves (Chapter 1, Table 1.6). Here that review is an approval of one proposal, bound to the diff's hash and the
evidence bundle's hash together. Only then does the bot open a pull request, through Chapter 18's effect
ledger, so a repeated run opens it once. Merging is not a function of this package: the bot's GitHub App cannot
approve or merge, branch protection lets only maintainers merge, and a change to a pipeline path also passes
Chapter 15's pipeline guard. Deploying is the pipeline's job, never the bot's.

Who may approve, in check order, each refusal written to the audit trail before it is raised:

  bad_person_proof / not_a_person   the decider is authenticated by a fresh proof from the person issuer
                                    (Chapter 10's gate), so the bot itself, or any agent, can never approve
  bot_owner_may_not_approve         the person accountable for the bot does not approve the bot's work
  not_a_code_owner:<path>           the decider owns every path the proposal touches (CODEOWNERS)
  not_in_an_approval_team           and is in one of the task type's approval teams
  security_review_required          a sensitive package or a security task type needs @relay/security
  (then the gate's own rules: expired, not_pending)

The paths, the diff's hash and the packages are computed here from the changed files themselves (`changes`), and
stored with the proposal; a caller cannot under-report what a change touches. Every package named in a changed lock
file counts, so leaving a sensitive package out of the list does not avoid a security review.

Before each step that has an effect (asking for an approval, opening the pull request) the bot verifies its own
token, so a kill-switch trip (Chapter 14) stops it at the next step; the refusal is audited and the run ends.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Callable

from ..agents import ApprovalGate, ApprovalRefused
from ..agents.session import AgentRevoked, AgentSession
from ..agentops.effects import EffectConflict, EffectLedger
from ..audit import AuditTrail
from .evidence import Bundle
from .updates import read_lock
from .policy import CodeOwners, Policy, approver_problem

SCHEMA = """
CREATE TABLE IF NOT EXISTS maintenance_proposals (
    proposal_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    task_type       TEXT NOT NULL,
    paths           TEXT NOT NULL,
    packages        TEXT NOT NULL,
    diff_sha256     TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL,
    approval_id     TEXT,
    status          TEXT NOT NULL,
    pr_number       INTEGER,
    attempt         INTEGER NOT NULL,
    decided_at      REAL,
    base            TEXT NOT NULL,
    stale_at        REAL
);
"""
APPROVAL_FRESH_SECONDS = 24 * 3600  # an approval older than this is stale: the mirror and main may have moved on
LIVE = ("awaiting_approval", "approved", "opened")


class ProposalRefused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    run_id: str
    task_id: str
    task_type: str
    paths: tuple[str, ...]
    packages: tuple[str, ...]
    diff_sha256: str
    evidence_sha256: str
    approval_id: str | None
    status: str
    pr_number: int | None


def diff_sha256(changes: dict[str, str]) -> str:
    """The hash an approval binds: every changed path with its new content, in a canonical form."""
    import hashlib
    body = json.dumps({k: changes[k] for k in sorted(changes)}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


_REQ = re.compile(r"^([A-Za-z0-9._-]+)\s*==\s*[^\s\\;]+")


def is_lock(path: str) -> bool:
    base = path.rsplit("/", 1)[-1].casefold()
    return base.endswith(".lock") or (base.startswith("requirements") and base.endswith(".txt"))


def lock_packages(changes: dict[str, str]) -> tuple[set[str], list[str]]:
    """(every package named in a changed lock file, the lock files with a line this reader cannot read).

    A lock file is any path whose name ends in `.lock` or is `requirements*.txt`. Each requirement line, wrapped or
    on one line with its `--hash`, must be `name==version`; option lines (`--...`), comments and blanks are skipped.
    Any other line makes the file unreadable, and the desk refuses rather than guess which packages it names.
    """
    names: set[str] = set()
    unreadable: list[str] = []
    for path, text in sorted(changes.items()):
        if not is_lock(path):
            continue
        names |= set(read_lock(text))
        for line in text.replace("\r\n", "\n").split("\n"):
            s = line.strip()
            if not s or s.startswith(("#", "-")):
                continue
            m = _REQ.match(s)
            if m is None:
                unreadable.append(path)
                break
            names.add(m.group(1).lower())
    return names, unreadable


class ProposalDesk:
    def __init__(self, policy: Policy, owners: CodeOwners, gate: ApprovalGate, trail: AuditTrail,
                 ledger: EffectLedger, session: AgentSession, stamp: Callable[[], str], head: Callable[[], str],
                 db: str = ":memory:") -> None:
        """`head()` returns the commit the default branch points at now, read from the code host, never from the bot.
        A proposal is bound to the head it was made against."""
        self.policy, self.owners, self.gate, self.trail = policy, owners, gate, trail
        self.head = head
        self.ledger, self.session, self.stamp = ledger, session, stamp
        self.conn = sqlite3.connect(db, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ audit helpers

    def _audit(self, action: str, resource: str, outcome: str, **detail) -> None:
        self.trail.append(agent_id=self.policy.agent_id, owner=self.policy.bot_owner, action=action,
                          resource=resource, outcome=outcome, source="relay.maintenance", at=self.stamp(),
                          detail=detail)

    def _refuse(self, action: str, resource: str, code: str, **detail) -> ProposalRefused:
        self._audit(action, resource, "refused", code=code, **detail)
        return ProposalRefused(code)

    def _alive(self, action: str, resource: str) -> None:
        try:
            self.session.verify(None)
        except AgentRevoked as exc:
            raise self._refuse(action, resource, f"{exc.status}:{exc.code}") from None

    def get(self, proposal_id: str) -> Proposal:
        row = self.conn.execute("SELECT * FROM maintenance_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        d = dict(row)
        return Proposal(d["proposal_id"], d["run_id"], d["task_id"], d["task_type"], tuple(json.loads(d["paths"])),
                        tuple(json.loads(d["packages"])), d["diff_sha256"], d["evidence_sha256"], d["approval_id"],
                        d["status"], d["pr_number"])

    # ------------------------------------------------------------------ the bot's side

    def propose(self, run_id: str, task_id: str, task_type: str, changes: dict[str, str], packages: list[str],
                bundle: Bundle) -> Proposal:
        """Record a proposal and ask for its approval, or refuse it (audited) and hand the task back.

        Refusals: unknown_task_type, tier_does_not_allow_changes (T0/T1), protected_path:<p>, not_writable:<p>,
        no_changes, unreadable_lock:<p>, evidence_blocking:<ids>; and revoked:* when the bot's own token is refused.

        The same change with the same evidence, while its proposal is still live (awaiting approval, approved or
        opened), returns that proposal and asks for nothing new. After a denial it becomes a new attempt with its own
        ID and approval request. After a stale approval the evidence must have run again since (`bundle.ran_at`
        after the moment the approval went stale), or the proposal is refused as `evidence_not_fresh`.
        """
        resource = f"task:{task_id}"
        paths = sorted(changes)
        found, unreadable = lock_packages(changes)
        packages = sorted(set(packages) | found)
        diff = diff_sha256(changes)
        t = self.policy.task_types.get(task_type)
        if t is None:
            raise self._refuse("maintenance.propose", resource, "unknown_task_type")
        if t.tier in ("T0", "T1"):
            raise self._refuse("maintenance.propose", resource, "tier_does_not_allow_changes", tier=t.tier)
        if not paths:
            raise self._refuse("maintenance.propose", resource, "no_changes")
        for p in sorted(paths):
            if self.policy.protected(p):
                raise self._refuse("maintenance.propose", resource, f"protected_path:{p}")
            if not self.policy.writable(task_type, p):
                raise self._refuse("maintenance.propose", resource, f"not_writable:{p}")
        if unreadable:
            raise self._refuse("maintenance.propose", resource, f"unreadable_lock:{unreadable[0]}")
        blocking = bundle.blocking()
        if blocking:
            raise self._refuse("maintenance.propose", resource, "evidence_blocking:" + ",".join(blocking),
                               evidence_sha256=bundle.sha256())
        self._alive("maintenance.propose", resource)
        evidence_sha = bundle.sha256()
        stale = self.conn.execute("SELECT MAX(stale_at) FROM maintenance_proposals WHERE task_id = ? AND "
                                  "diff_sha256 = ? AND status IN ('stale', 'base_moved')",
                                  (task_id, diff)).fetchone()[0]
        if stale is not None and (bundle.ran_at is None or bundle.ran_at <= stale):
            raise self._refuse("maintenance.propose", resource, "evidence_not_fresh")
        rows = self.conn.execute("SELECT proposal_id, status FROM maintenance_proposals WHERE task_id = ? AND "
                                 "diff_sha256 = ? AND evidence_sha256 = ? ORDER BY attempt",
                                 (task_id, diff, evidence_sha)).fetchall()
        if rows and rows[-1]["status"] in LIVE:
            return self.get(rows[-1]["proposal_id"])
        attempt = self.conn.execute("SELECT COUNT(*) FROM maintenance_proposals WHERE task_id = ? AND diff_sha256 = ?",
                                    (task_id, diff)).fetchone()[0] + 1
        proposal_id = f"mp-{task_id}-{diff[:12]}-{attempt}"
        base = self.head()
        args = {"proposal_id": proposal_id, "diff_sha256": diff, "evidence_sha256": evidence_sha, "base": base}
        approval = self.gate.request(run_id, "maintenance_proposal", args, "another_person", self.policy.agent_id,
                                     self.policy.bot_owner, bound={"diff_sha256": diff,
                                                                   "evidence_sha256": evidence_sha})
        self.conn.execute("INSERT INTO maintenance_proposals (proposal_id, run_id, task_id, task_type, paths, packages,"
                          " diff_sha256, evidence_sha256, approval_id, status, attempt, base) VALUES"
                          " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (proposal_id, run_id, task_id, task_type, json.dumps(sorted(paths)),
                           json.dumps(packages), diff, evidence_sha, approval.approval_id,
                           "awaiting_approval", attempt, base))
        self._audit("maintenance.propose", resource, "awaiting_approval", proposal_id=proposal_id,
                    approval_id=approval.approval_id, diff_sha256=diff, evidence_sha256=evidence_sha)
        return self.get(proposal_id)

    # ------------------------------------------------------------------ the person's side

    def decide(self, proposal_id: str, proof: dict, approve: bool, reason: str) -> Proposal:
        """A person approves or denies a proposal. Every refusal is audited, then raised as ApprovalRefused."""
        p = self.get(proposal_id)
        resource = f"proposal:{proposal_id}"
        try:
            person = self.gate.authenticate(proof)
        except ApprovalRefused as exc:
            self._audit("maintenance.approval", resource, "refused", code=exc.code)
            raise
        problem = approver_problem(self.policy, self.owners, person, p.task_type, list(p.paths), list(p.packages))
        if problem is not None:
            self._audit("maintenance.approval", resource, "refused", code=problem, person=person)
            raise ApprovalRefused(problem)
        try:
            approval = self.gate.decide(p.approval_id, proof, approve, reason)
        except ApprovalRefused as exc:
            self._audit("maintenance.approval", resource, "refused", code=exc.code, person=person)
            raise
        status = "approved" if approval.status == "approved" else "denied"
        self.conn.execute("UPDATE maintenance_proposals SET status = ?, decided_at = ? WHERE proposal_id = ?",
                          (status, self.gate.clock(), proposal_id))
        self._audit("maintenance.approval", resource, status, person=person)
        return self.get(proposal_id)

    # ------------------------------------------------------------------ after approval

    def open_pull_request(self, proposal_id: str, changes: dict[str, str], evidence_sha256: str,
                          open_pr: Callable[[str, dict], dict]) -> dict:
        """Open the approved proposal's pull request once (effect key `pr:maint:<task>`).

        The changed files and the evidence the bot holds now must hash to the ones approved; a change after approval
        needs a new proposal. An approval older than APPROVAL_FRESH_SECONDS is stale: the proposal is marked so and
        must be made again, with fresh evidence. The default branch must still be at the commit the proposal was made
        against: the change is whole files, so a pull request on a moved base could undo someone's change
        (`base_moved`). The effect is keyed by the proposal, so each approved attempt opens at most one pull request.
        Refusals: not_approved, approval_stale, base_moved, changed_since_approval, effect_conflict, and revoked:*
        from the kill switch.
        """
        p = self.get(proposal_id)
        resource = f"proposal:{proposal_id}"
        if p.status not in ("approved", "opened"):
            raise self._refuse("maintenance.open_pr", resource, "not_approved", status=p.status)
        row = self.conn.execute("SELECT decided_at, base FROM maintenance_proposals WHERE proposal_id = ?",
                                (proposal_id,)).fetchone()
        now = self.gate.clock()
        if p.status == "approved" and now - row["decided_at"] > APPROVAL_FRESH_SECONDS:
            self.conn.execute("UPDATE maintenance_proposals SET status = 'stale', stale_at = ? WHERE proposal_id = ?",
                              (now, proposal_id))
            raise self._refuse("maintenance.open_pr", resource, "approval_stale", age_s=round(now - row["decided_at"]))
        if p.status == "approved" and self.head() != row["base"]:
            self.conn.execute("UPDATE maintenance_proposals SET status = 'base_moved', stale_at = ? "
                              "WHERE proposal_id = ?", (now, proposal_id))
            raise self._refuse("maintenance.open_pr", resource, "base_moved")
        if (diff_sha256(changes), evidence_sha256) != (p.diff_sha256, p.evidence_sha256):
            raise self._refuse("maintenance.open_pr", resource, "changed_since_approval")
        self._alive("maintenance.open_pr", resource)
        args = {"task": p.task_id, "diff_sha256": p.diff_sha256, "evidence_sha256": p.evidence_sha256}
        try:
            result, replayed = self.ledger.perform(f"pr:maint:{proposal_id}", "pull_request", args, p.run_id, open_pr,
                                                   provider_idempotent=True, provider_window_s=86_400.0)
        except EffectConflict:
            raise self._refuse("maintenance.open_pr", resource, "effect_conflict") from None
        self.conn.execute("UPDATE maintenance_proposals SET status = 'opened', pr_number = ? WHERE proposal_id = ?",
                          (result.get("number"), proposal_id))
        self._audit("maintenance.open_pr", resource, "ok", number=result.get("number"), replayed=replayed)
        return {**result, "replayed": replayed}
