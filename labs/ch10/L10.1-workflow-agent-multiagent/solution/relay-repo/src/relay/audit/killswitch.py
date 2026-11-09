"""The kill switch for one agent identity (added in 4.23.0; ADR-022).

Tripping it does three things inside Relay at once: the agent is disabled, its epoch moves on so
every token it holds is refused on next use, and the trip is written to the audit trail. It also
returns the cloud, GitHub and ECS steps the runbook (`infra/runbooks/kill-switch.md`) carries out,
because an agent that is refused by Relay may still hold cloud credentials from its role or a GitHub
installation token.

What no switch recalls: values the agent has already read, such as a secret injected into its task's
environment, and connections it already holds open, such as a database session. Those end only when
its tasks stop, which is why stopping running work is a step of its own.

The asymmetry is deliberate. Automation may trip the switch (a detection rule can), because
removing access is the safe direction. Only people may restore it, and only two of them: the
person restoring and a second person who reviewed why it was tripped. Restoring never revives an
old token. For an agent with a cloud role it must not revive an old *proof* either: credentials
copied before the trip can still sign `sts:GetCallerIdentity`, which no deny policy stops. So such an
agent is restored only under a new role (a new registry subject), or once the longest lifetime of
its role's credentials has passed since the trip.

Limit in 4.23.0: `restore` compares two names. Until Relay's admin path authenticates both people,
the two-person rule is a check on what the caller says, not on who the caller is.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .identity import AgentRegistry
from .trail import AuditTrail

QUARANTINE_POLICY = "relay-nonprod-agent-quarantine"
# The longest any credential issued for an agent's cloud role can live, in seconds. ECS task-role
# credentials are rotated by ECS; this bound is an assumption to check against AWS's documentation.
CLOUD_CREDENTIAL_MAX_SECONDS = 6 * 3600


class RestoreRefused(Exception):
    pass


@dataclass(frozen=True)
class KillSwitchResult:
    agent_id: str
    epoch: int
    actor: str
    record_hash: str
    external_steps: tuple[str, ...]


def quarantine_policy() -> dict:
    """The managed policy the kill-switch role attaches to an agent's cloud role: deny everything.

    An explicit deny in an attached policy applies to sessions already issued for the role, once
    the change has propagated; nothing about the session itself needs to be revoked.
    """
    return {"Version": "2012-10-17",
            "Statement": [{"Sid": "AgentQuarantined", "Effect": "Deny", "Action": "*", "Resource": "*"}]}


def revoke_older_sessions_policy(issued_before: str) -> dict:
    """Deny sessions issued before a time (`aws:TokenIssueTime`; ISO 8601 UTC). It stops copied
    credentials calling AWS services; it does not stop them signing `sts:GetCallerIdentity`."""
    return {"Version": "2012-10-17",
            "Statement": [{"Sid": "RevokeOlderSessions", "Effect": "Deny", "Action": "*", "Resource": "*",
                           "Condition": {"DateLessThan": {"aws:TokenIssueTime": issued_before}}}]}


def trip(registry: AgentRegistry, trail: AuditTrail, agent_id: str, actor: str, reason: str,
         at: str | None = None, now: float | None = None) -> KillSwitchResult:
    """Disable `agent_id` now. `actor` is a person or an automation label such as "detection:DR-001"."""
    agent = registry.disable(agent_id, at=time.time() if now is None else now)
    record = trail.append(agent_id=agent_id, owner=agent.owner, action="killswitch.trip",
                          resource=f"agent:{agent_id}", outcome="ok", source="killswitch", at=at,
                          detail={"actor": actor, "reason": reason, "epoch": agent.epoch})
    steps = [f"relay: {agent_id} disabled; every token issued before epoch {agent.epoch} is refused"]
    if agent.cloud_role:
        steps.append(f"aws: attach {QUARANTINE_POLICY} to {agent.cloud_role}")
    if agent.kind == "ecs-task":
        steps.append(f"aws: set desired count 0 on ECS services tagged agent={agent_id}, then stop its running tasks")
    if agent.kind == "ci-job":
        env = agent.subject.rpartition(":environment:")[2] or agent.subject
        steps.append(f"github: cancel running workflow runs in environment {env}")
    if agent.github_app:
        steps.append(f"github: revoke {agent.github_app} installation tokens issued to {agent_id} and suspend "
                     f"the installation")
    return KillSwitchResult(agent_id, agent.epoch, actor, record["hash"], tuple(steps))


def restore(registry: AgentRegistry, trail: AuditTrail, agent_id: str, actor: str, reviewed_by: str,
            at: str | None = None, now: float | None = None, new_subject: str | None = None,
            new_cloud_role: str | None = None) -> None:
    """Re-enable `agent_id`. Both `actor` and `reviewed_by` must be people, and different people.

    An agent with a cloud role is restored only with `new_subject` (and its new role), or once
    CLOUD_CREDENTIAL_MAX_SECONDS have passed since the trip.
    """
    if actor not in registry.people or reviewed_by not in registry.people:
        raise RestoreRefused("only people may restore an agent")
    if actor == reviewed_by:
        raise RestoreRefused("restoring needs a second person's review")
    agent = registry.get(agent_id)
    now = time.time() if now is None else now
    if agent.cloud_role and new_subject is None and (
            agent.tripped_at is None or now - agent.tripped_at < CLOUD_CREDENTIAL_MAX_SECONDS):
        raise RestoreRefused("credentials copied before the trip may still sign workload proofs: restore under "
                             "a new role, or wait until they have expired")
    agent = registry.enable(agent_id, new_subject=new_subject, new_cloud_role=new_cloud_role)
    trail.append(agent_id=agent_id, owner=agent.owner, action="killswitch.restore", resource=f"agent:{agent_id}",
                 outcome="ok", source="killswitch", at=at,
                 detail={"actor": actor, "reviewed_by": reviewed_by, "epoch": agent.epoch,
                         "new_subject": new_subject is not None})
