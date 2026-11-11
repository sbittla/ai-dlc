# ADR-056 — Governing autonomy: no self-modification, a safety and security case for any exception, and evidence criteria before T4

Status: accepted
Date: 2027-06-02
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering), lena.k (product)
Links: ESC-N01, ESC-N03, CON-1
Related: ADR-021, ADR-022, ADR-026, ADR-029, ADR-045, ADR-047, ADR-053, ADR-054
Revisit when: any task type passes relay-autonomy-criteria-v1; Chapter 12's live attack measurement reports; or a
safety and security case is proposed for a self-modifying task type. Review by 2027-12-02 in any case.

## Context

ADR-026 made approval gates part of every run with an external effect, and named its revisit condition: a task
type moving to T4 under Chapter 19's rules. Chapter 1 said no agent approves its own work, and that T4 means a
person approves a policy in advance and audits the outcomes. Chapter 12 said a task that reads untrusted input stays
at T2 until its coverage gate passes and a live measurement exists. On 10 May the old dependency bot's rule was
widened to minor updates after a clean run of patch merges, and ten days later it locked every user out.

## Options considered

### Option A — Protected paths and an independent approver for every change; any self-modifying or T4 task type needs a written case or evidence criteria, then two people

### Option B — Raise a task type to T4 when its last month has no incident

### Option C — Let the bot review its own pull requests with a second model before merging

## Decision

Option A.

- **No self-modification.** The bot never writes a protected path (ADR-053); paths compare case-folded. The
  loader refuses any task type marked `self_modification` (`relay.maintenance.policy.validate`): supporting one
  needs a new ADR, a safety and security case approved under the pipeline guard, and a reviewed loader change.
- **The policy is pipeline configuration.** From 4.31.0 `governance/pipeline-guard.json` lists `maintenance/`,
  `src/relay/maintenance/` and the bot's tests as pipeline paths, and `maintenance/` as gate configuration. A
  change to the policy, an eligibility report or the DST rules travels alone, with two approvals (one from the
  platform leads) and an approval from `@relay/security` (PG001 to PG003).
- **Never its own approver, merger or deployer.** Approvals need a person's proof; the App cannot approve or
  merge; the pipeline deploys. The person accountable for the bot does not approve its proposals.
- **Safety and security cases** use Claims-Arguments-Evidence: one top claim, sub-claims, evidence items with the
  strength they need (verified, deployed, modelled) and defeaters. `relay.maintenance.safety_case.check` binds each
  item to a recorded result and lists every gap: undeveloped claims, missing or failing results, weak evidence,
  open defeaters and approvals that break the two-person rule.
- **Metrics** per task type (`relay.maintenance.autonomy`): task success, regression and rollback rates among
  merged changes, intervention frequency, policy violations and cost per run and per success, with Wilson 95%
  intervals; two policies are compared only on the same tasks, with an exact McNemar test.
- **relay-autonomy-criteria-v1** for a T4 grant, all required, failing closed: A1 the Wilson upper bound of harm
  (regression or rollback) among merged changes at most 5%, which at zero harms takes 73 merged changes; A2 the
  upper bound of interventions at most 10%; A3 no policy violations; A4 for a task type that reads untrusted input,
  Chapter 12's coverage gate passing and its live attack measurement recorded; A5 a kill-switch drill and A6 a
  rollback drill within 90 days; A7 the scanners' measured catch rate on record, counted as context, never alone.
  A drill counts only if it ran on the deployed system, 0 to 90 days before the report. Passing makes a
  candidate. A grant names three files under `maintenance/eligibility/`: the report (with its SHA-256), the
  outcome log and the evidence file. The loader recomputes the report from the log and the evidence with
  `eligibility_report` and refuses one that differs, so a hand-edited report fails; it derives whether a task
  type reads untrusted input from what starts it (`TRUSTED_INPUT_TASK_TYPES`); and it enforces Chapter 12's cap:
  any tier above T2 for an untrusted reader needs A4 passed. It cannot tell whether the log and the evidence are
  true, nor authenticate people, so a grant that types a verdict or approver names is refused and the code
  host's review under the pipeline guard is the control. This replaces ADR-026's per-call approval
  gates for that task type only, and only within the grant's limits.

## Consequences

- No task type qualifies in Lab 19.1's simulated month (9 June to 9 July 2027; the bot did not run in June):
  every type fails A5 and A6, since no drill has run on a deployed bot. Dependency updates have one
  rollback in 16 merged changes (harm upper bound 28.3%) and interventions on 8 of 22 runs; documentation upkeep has
  zero harms in 11 merged changes (upper bound 25.9%) but 4 policy violations from one steered report; no live
  attack measurement is recorded, so every task type that reads untrusted input fails A4.
- A task type done once a year, such as the table extension, can never meet A1; it stays at T2 for good.
- The grant's eligibility report and the safety case are files a person reviews; this code checks their structure
  and the results they cite, not whether the claims are the right ones.

## Rejected alternatives

### Option B — Raise a task type to T4 when its last month has no incident
Rejected because: a month of clean runs is a small sample; zero harms in 11 merged changes still leaves an upper bound near 26%, and the old bot's rule was widened on exactly that kind of record.
Revisit if: never as stated; A1 is the same idea with the sample size made explicit.

### Option C — Let the bot review its own pull requests with a second model before merging
Rejected because: a second model shares the first one's inputs, including the untrusted report, and its approval is still the bot approving its own change.
Revisit if: a reviewing model becomes one more evidence item, never the approver.
