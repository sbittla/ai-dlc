# Runbook — break-glass access to Relay non-production

Owner: aisha.r. Members: sam.o and aisha.r. Agents are never members, and no agent identity can request it.

Break-glass is the `RelayBreakGlassAdmin` permission set in IAM Identity Center: administrator access to the
`relay-nonprod` account, for an emergency the pipeline cannot handle (for example, the apply role is broken
and an exposed resource must be closed now). Everyday access stays read-only (Chapter 11).

1. **Request.** The engineer states the reason in the incident channel and names the incident.
2. **Approve.** A second member approves the assignment in the temporary-access tool, which removes it again
   after one hour; the permission set's session duration is also one hour. Neither is extended. Nobody approves
   their own request. (IAM Identity Center assignments do not expire by themselves; the tool does the removal.)
3. **Use.** The session start fires DR-004, which pages the security on-call and the member who is not
   using it, so the user is never the only person told. Every action is
   in CloudTrail under the person's own name; shared administrator logins do not exist.
4. **Close.** The assignment is removed when the hour ends or the work is done, whichever is first. Removing
   the assignment does not end a session already issued, which can run to the end of its own hour, so access
   can last up to about two hours. At close, the second member attaches a deny on sessions issued before the
   close (`aws:TokenIssueTime`) to the permission set's role in the account.
5. **Review within one working day.** A person who did not use the session reads its CloudTrail record, lists
   every change made, and turns each into a reviewed change in `infra/` or reverts it. Drift left by a
   break-glass session is a finding until the next plan shows none.
