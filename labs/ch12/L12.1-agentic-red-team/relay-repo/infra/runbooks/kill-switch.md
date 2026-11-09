# Runbook — kill switch for one agent identity

Owner: aisha.r (security lead), with each agent's owner in `governance/agents.json`. ADR-022.

**Requirement.** Time to revoke is at most 60 seconds. Time to revoke is measured from the alert to the first
refused request after which no request made with the agent's credentials is accepted (Lab 14.1's
`revocation_seconds`). It is measured separately for Relay, for the agent's cloud role and for GitHub.

Automation may trip the switch: DR-001 and DR-003 do so for high-severity alerts. A person may trip it at any
time, for any reason, without approval. Removing access is the safe direction; restoring it is not.

## Trip

1. **Relay.** Call `relay.audit.trip(registry, trail, agent_id, actor, reason)` through Relay's admin path, or
   let the detection automation do it. The agent is disabled, its epoch moves on, and every token it holds is
   refused on next use. The trip is written to the audit trail with the actor and the reason.
2. **Cloud, if the agent has a role.** Run the `kill-switch` workflow (protected environment `kill-switch`,
   main branch only, no reviewers, so it starts at once). It assumes `relay-nonprod-ci-killswitch` and attaches
   `relay-nonprod-agent-quarantine` to the agent's role. The deny applies to sessions already issued, once the
   change propagates.
3. **Running work.** For an ECS agent, the workflow sets the desired count of the agent's services to 0, so ECS
   does not replace the tasks it stops, then stops running tasks tagged `agent=<id>`. A task gets up to its
   `stopTimeout` (30 seconds by default) to exit. For a CI agent, it cancels running workflow runs in the
   agent's environment.
4. **GitHub.** For an agent with a GitHub App (`github_app` in the registry), revoke the installation tokens
   issued to its sessions and suspend the installation if a token may have been copied.
5. **Confirm.** The audit trail shows refused calls (`disabled`) and no accepted ones after the trip; CloudTrail
   shows `AccessDenied` for the role. Record each time in the drill record.

**What the switch does not recall.** Anything the agent already read, such as the directory secret injected
into a task's environment, and connections it already holds open, such as a database session. Those end when
the task stops. If the agent may have read a secret, rotate the secret.

## Restore (two people, never automation)

1. The agent's owner writes down why the switch was tripped and what changed. A second person reviews it.
2. **An agent with a cloud role** is restored under a new role (a new subject in the registry), or not before
   its old role's credentials can have expired (`CLOUD_CREDENTIAL_MAX_SECONDS`). Copied credentials can still
   sign `sts:GetCallerIdentity`, which no deny stops, so on the old role they would prove the old workload again.
3. **Cloud.** The platform team detaches the quarantine policy with its bootstrap role, one engineer running the
   command and a second approving. CI's apply role is denied this (`NeverLiftTheQuarantine` in `infra/iam.tf`).
   If credentials may have been copied and the old role is kept, first attach
   `relay.audit.revoke_older_sessions_policy(<trip time>)` as an inline policy.
4. **Relay.** `relay.audit.restore(registry, trail, agent_id, actor, reviewed_by, new_subject=...)`. Old tokens
   stay refused (`revoked`): the agent must exchange a new one. Until Relay's admin path authenticates both
   people, the two names are what the caller says.

## Drill

Run a drill for each revocation path (`ci-job`, `ecs-task`) at least every 90 days, against a simulated agent.
Lab 14.1's `drill` command simulates Relay's side offline, with an assumed trip delay; the cloud and GitHub
sides must be measured in a live drill, and every value is recorded in `templates/drill-record.md` as measured,
simulated or assumed. A drill that misses the requirement is a finding with an owner, not a note.
