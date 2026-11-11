# ADR-053 — A maintenance bot at tier T2: a workflow with one agent step, its own identity, and a person's approval of each proposal

Status: accepted
Date: 2027-05-27
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering; the bot's owner)
Links: ESC-N03, CON-1
Related: ADR-020, ADR-024, ADR-025, ADR-026, ADR-034, ADR-045, ADR-049, ADR-050, ADR-054, ADR-055, ADR-056
Revisit when: a task type passes relay-autonomy-criteria-v1 (ADR-056); the bot needs a tool beyond the four in its
agent step; or a second repository's maintenance moves onto it. Review by 2027-11-27 in any case.

## Context

On Thursday 20 May 2027 a rule-based dependency bot merged sessionkeel 2.4.1 to 2.5.0 into the web application's
repository, outside the teaching snapshot, where an older rule still let it merge. Its rule had been widened on
10 May to merge minor updates when checks pass. 2.5.0 changed a default: `verify` now required an audience, and
the tokens Relay's sign-in issues carry none. Every check passed; the canary judged the release healthy, because a
401 is good for the availability SLI (ADR-037). From 14:47 to 16:47 UTC nobody could sign in. Lab 19.1 reproduces
the sequence with a fictional package and generated counts.

Relay still needs maintenance done: dependency and vulnerability updates, broken documentation links, bug reports
to reproduce, and dated data such as ADR-010's daylight-saving table, due for review by 2027-09-30. Eight engineers
(CON-1) cannot do all of it by hand, and the reports arrive as text that outsiders write.

## Options considered

### Option A — A workflow with one bounded agent step, at T2, under its own identity, proposing changes a person approves

### Option B — Keep the rule-based bot, narrowed back to patch updates, with auto-merge

### Option C — A general coding agent given the maintenance backlog, opening pull requests on its own judgement

### Option D — No automation: maintenance stays on the team's backlog

## Decision

Option A. The maintenance bot (`maintenance-bot` in `governance/agents.json`) runs `relay.maintenance`:

- **Deterministic where it can be.** Reports become tasks from structured fields only (`reports.triage`); free
  text is untrusted data. Versions come from the mirror only (ADR-054). Checks run in Chapter 18's sandbox.
- **One agent step**, for documentation fixes and bug reproductions, behind Chapter 10's boundary with four tools
  (`read_report`, `read_file`, `edit_file`, `run_tests`); no tool opens, approves or merges anything, and none
  reaches the network. Reading a report taints the run (ADR-034).
- **Its own identity and app.** A `ci-job` identity under the `maintenance` environment's OIDC subject, owner
  priya.n, 15-minute tokens, no cloud role; its own GitHub App `relay-maintenance` with contents and pull requests
  only, no workflows permission, in no CODEOWNERS team and on no bypass list. A kill-switch trip refuses its next
  token use; the proposal desk verifies the token before each effect.
- **T2 for every task type** (`maintenance/policy.json`, relay-maintenance-policy-v1; bug reproduction is T1). A
  proposal is approved by one person who owns every path it touches, is in the task type's approval team, is not
  the bot's owner, and is in `@relay/security` for a sensitive package or a security task type. The approval binds
  the diff's hash and the evidence bundle's hash. Only then does the bot open a pull request, once, through the
  effect ledger (ADR-049). Merging is branch protection's: maintainers only, no apps. A dependency PR changes a
  pipeline path and so also passes the pipeline guard (ADR-045). Deploying is the pipeline's.
- **The bot cannot change itself.** The policy's protected paths cover its instructions, its workflow and all of
  `.github/`, `governance/`, the policy, its own code and runtime, the scanners and checks, and its own tests. The
  boundary's write list and the proposal desk each refuse them, and every refusal is audited (ESC-N03).
- The workflow (`.github/workflows/maintenance.yml`) starts on a schedule or by hand, never on an issue or comment
  event, runs on the agent sandbox's ephemeral runners and reads the policy from main.

## Consequences

- Lab 19.1: on the 20 May update the bot's own checks block the proposal (`evidence_blocking:E3,E4`: the round
  trip and the pinned defaults fail; the app's tests pass). Replaying the advisory of 9 June, it reproduces, proposes
  sessionkeel 2.4.2 with six evidence items, refuses the bot, its owner and a non-owner as approvers, and opens one
  pull request after aisha.r approves. A steered agent step is refused four times and changes no file.
- Every maintenance change waits for a person; the bot saves the finding, the reproduction and the evidence, not
  the review. Intervention frequency in the simulated month is reported, not hidden (ADR-056).
- Not built in 4.31.0: the bot's runner and its scheduled deployment (the workflow names an illustrative runner;
  owner priya.n, by 2027-08-31); the `relay-maintenance` App (platform leads, as for `relay-spec-to-pr`); team
  membership is declared in the policy and must be checked against GitHub's settings. The OIDC subject names the
  `maintenance` environment and not a branch, so the environment must accept deployments from `main` only, a
  code-host setting (platform leads, by 2027-07-30).
- Two controls stop a protected edit (the boundary's write list and the desk) and share one process and one
  policy file: they are one failure domain. The independent controls are the App's permissions and branch
  protection, outside Relay.

## Rejected alternatives

### Option B — Keep the rule-based bot, narrowed back to patch updates, with auto-merge
Rejected because: the incident's change claimed to be a minor update, and Lab 19.1's replay has a patch that broke production too; a version number is the maintainer's claim, not evidence about defaults or behaviour.
Revisit if: a task type passes relay-autonomy-criteria-v1 and two people approve a grant (ADR-056).

### Option C — A general coding agent given the maintenance backlog, opening pull requests on its own judgement
Rejected because: it reads untrusted reports with write tools and broad repository access, Chapter 12's coverage gate does not cover that combination, and nothing would bind a person's review to the evidence.
Revisit if: never for untrusted reports; a narrower agent for one task type is a new task type in this policy.

### Option D — No automation: maintenance stays on the team's backlog
Rejected because: ADR-010's table runs out on 2027-12-31, advisories need reproducing within days, and the backlog of link fixes and dependency updates already outruns eight engineers.
Revisit if: the bot's intervention frequency stays above half its runs for a quarter, so that it saves no work.
