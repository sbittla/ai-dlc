# Runbook — worker stalled, escalation passes failing, rules that cannot be evaluated

Owner: sam.o. Alerts: AL-001 (page), AL-002, AL-003 (tickets), AL-006 (page). ESC-N09, ESC-AC29, ADR-017.

A missed escalation is a missed page. The worker writes its heartbeat only after a pass whose escalation part
succeeded, so a worker that runs but cannot evaluate looks stalled, on purpose.

## AL-001: no completed pass for 5 minutes (page)

1. Acknowledge the page. Open `/healthz`: `worker.last_pass_age_s` and `worker.stalled`.
2. Check the worker task is running. If it is not, the service's own restart policy should have replaced it;
   find why it stopped (the task's stop reason) before starting another.
3. If it is running, look for `escalation pass failed` log records and the `relay.escalation.passes{failed}`
   counter (AL-003). The span `worker.pass` with status ERROR links to the log line.
4. A database problem (locks, latency, a failed migration) is the usual cause: follow `db-latency.md`.
5. Restarting the worker is an approval-gated action (one person other than the requester). It does not fix a
   pass that fails on every run; it only clears a stuck process.
6. While the pass is down, P1 escalations are not firing. Tell the pilot workspaces' owners if it lasts more
   than 15 minutes (G1).

## AL-002: rules that cannot be evaluated (ticket)

A rule whose business-hours delay runs past the daylight-saving table (ADR-010) is skipped and recorded once
on the task as `cannot_evaluate`; every other rule still fires. Find the rule in the task's activity, tell its
project's Admins, and check whether ADR-010's table needs extending (review due 2027-09-30).

## AL-006: a P1 escalation held by the flood cap and not acknowledged (page)

D7's pilot review (`docs/slo/d7-pilot-review.md`) kept the cap for P1. A held P1 still reaches the
workspace's webhook. Check the task: if nobody has acknowledged it 10 minutes after it was held, call the
workspace's Owner through the support process. Record every AL-006 page for the next D7 review.
