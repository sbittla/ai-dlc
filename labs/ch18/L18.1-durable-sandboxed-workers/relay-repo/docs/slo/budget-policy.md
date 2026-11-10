# Error budget policy

Agreed by sam.o (tech lead), lena.k (product) and aisha.r (security), 2027-02-10. ADR-037. Reviewed each quarter.

The error budget is the share of a 30-day window's events an SLO allows to be bad. This policy says what
happens as it is spent. It applies per SLO, to the service that owns it.

1. **Budget remaining below 25%.** The owner reviews the risk of the next release before it ships on the
   15:00 train, and says in the release note why it is safe.
2. **Budget exhausted (below 0%).** Feature releases for the owning service stop. Reliability fixes, security
   fixes and changes that reduce risk still ship. Releases resume when the budget is above 0% again.
3. **One event spent at least 20% of the budget.** It gets a blameless postmortem within 5 working days, with
   action items typed as spec, test, eval, adversarial eval, detection or runbook.
4. **AI objectives.** When SLO-TRIAGE-QUALITY or SLO-TRIAGE-SAFETY is exhausted, no prompt, model or routing
   change for triage ships until the cause is found, and Chapter 7's gate runs on the newest labelled
   tickets before any change resumes.
5. **Disagreements.** If the owner thinks the budget was spent by something outside the service's control
   (a provider outage, an attack), the tech lead decides, and the decision is written down. An attack still
   counts against the budget; it is the reason for the security work, not an exemption from it.

Exceptions to item 2 need the tech lead and the product owner, in writing, with an end date.
