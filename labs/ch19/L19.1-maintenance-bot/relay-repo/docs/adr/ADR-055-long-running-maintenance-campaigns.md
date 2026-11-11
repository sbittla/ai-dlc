# ADR-055 — Long-running maintenance as campaigns on the agent job queue, with checkpoints, budgets, cancellation and escalation

Status: accepted
Date: 2027-06-01
Decided by: sam.o (architect of record)
Reviewed by: aisha.r (security), priya.n (engineering)
Links: ESC-N03, CON-1
Related: ADR-010, ADR-024, ADR-026, ADR-049, ADR-053
Revisit when: a campaign needs more than one worker at a time; the PostgreSQL adapter lands (the queue and run
store move with it); or a campaign is stopped by its budget more than once a month. Review by 2027-12-01 in any case.

## Context

Some maintenance is too large for one run: refreshing every dependency of a service, re-checking every
documentation link, extending ADR-010's table for the zones it covers. Such work runs for hours, crosses restarts,
spends money on model calls and must stop when a person says so. Chapter 10 gave runs budgets and approval-gated
raises; Chapter 18 gave durable jobs with leases, heartbeats, cancellation and dead letters.

## Options considered

### Option A — A campaign is one run in the run store and one job per item on the agent job queue

### Option B — One long agent run that loops over the items itself

### Option C — A workflow engine service for campaigns

## Decision

Option A (`relay.maintenance.longrun.Campaign`).

- The campaign's budget, status and checkpoint live in its run (`run-campaign:<id>`); each item is a job keyed
  `<campaign>:<item>`, so a repeated start adds nothing and a crashed worker's item is claimed again after its
  lease.
- After each item the worker heartbeats the job, then saves the meter and the lists of items done and handed back
  to the run. A new process resumes from that checkpoint, with what was spent still spent.
- Before each item the meter admits its estimate against what is left. When it does not fit, the campaign waits
  (`awaiting_approval`, `budget:<kind>`), the item goes back to the queue untouched, and the escalation is audited.
  Only a person other than the campaign's requester raises the budget (Chapter 10's `another_person` rule).
- A person cancels with their own proof. Queued items are cancelled at once; a running one at its next heartbeat,
  between steps. The run ends `stopped`.
- Three items handed back in a row, or any sandbox refusal, stop the campaign and escalate to the bot's owner.

## Consequences

- Relay's tests cover a crash after three of eight items (resumed to eight, $0.12 in all), budget exhaustion
  (three items for $0.09 against $0.10, five left queued), a raise refused to the requester and approved by sam.o,
  a cancellation while the second item runs (seven cancelled), three hand-backs in a row, and a sandbox refusal.
- One worker per campaign: items run in order. Parallel workers would need the meter's admission to be one
  transaction across workers.
- A campaign's step results stay in the run journal under ADR-049's retention item (owner sam.o).

## Rejected alternatives

### Option B — One long agent run that loops over the items itself
Rejected because: a crash loses the loop's place, the budget covers the whole loop rather than each item, and cancellation can only stop the run, not the items still queued.
Revisit if: never for work with external effects; ADR-049 already moved Relay's agents onto the queue.

### Option C — A workflow engine service for campaigns
Rejected because: it is a new service for eight engineers to run (CON-1), for work the existing queue and run store already handle at Relay's scale.
Revisit if: a workflow engine is adopted elsewhere in the company, as ADR-049 also says.
