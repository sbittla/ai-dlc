# INT-3 — Relay security lead

- Date: 2026-09-22
- Interviewer: lena.k (Relay product owner)
- Interviewee: aisha.r, Relay's security lead
- Method: video call, 30 minutes, recorded with consent; automatic transcript corrected by the interviewer
- Status: source document. Quote it; do not edit it.

**lena.k:** What's your view of escalation rules?

**aisha.r:** A rule is a way to send our customers' task titles to someone. So treat rule changes like permission changes.

**lena.k:** Who should be allowed to create them?

**aisha.r:** Only Owners and Admins should create or change rules. Members can see which rules apply to their projects, but not edit them.

**lena.k:** Who can a rule escalate to?

**aisha.r:** Never send an escalation to someone who can't see the project. Guests are fine for projects they're invited to, and nowhere else. And no addresses outside the workspace, ever.

**lena.k:** What else?

**aisha.r:** Every rule change goes in the audit log, with who changed it, when, and what it was before. Titles can contain customer data, so keep them out of anything that leaves Relay, like email. A link is enough.

**lena.k:** What abuse do you expect?

**aisha.r:** Someone will use a rule to flood a colleague with notifications. Cap it. Someone will try to escalate to an address outside the workspace. And a compromised account could change a rule quietly so that P1s go nowhere. Changing a P1 rule should be loud.

**lena.k:** The support team would like the triage model's P1 to start escalation automatically.

**aisha.r:** The AI priority is a suggestion. A person confirms a P1 before anything pages anyone. That's already our triage rule, and an injected ticket could otherwise page the whole on-call rota. Show the suggestion and how confident the model is, by all means, and let people override it.

**lena.k:** Security incidents?

**aisha.r:** Security incidents are always P1, and the security lead hears within an hour. No escalation rule may delay or switch that off.

**lena.k:** Any view on text messages?

**aisha.r:** SMS costs money per message and leaves our boundary. If you add it, someone has to own that budget, and the message can't carry the title.
