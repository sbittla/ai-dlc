# INT-2 — Relay support lead

- Date: 2026-09-17
- Interviewer: lena.k (Relay product owner)
- Interviewee: tomas.b, who leads Relay's own customer support team
- Method: in person, 35 minutes, notes typed during the conversation and read back to the interviewee
- Status: source document. Quote it; do not edit it.

**lena.k:** You run Relay's own support queue in Relay. What goes wrong with urgent tickets today?

**tomas.b:** Customer tickets come in, the triage model suggests a priority, and someone on my team confirms it. The tickets become tasks in our Support project. The problem is the gap after that. A P1 can be confirmed and then sit, because the person it's assigned to is in a meeting.

**lena.k:** What would you want instead?

**tomas.b:** Mirror what on-call does. If nobody acknowledges a P1 within ten minutes, the secondary gets paged. At twenty minutes it goes to the engineering manager. Everyone here already knows those numbers.

**lena.k:** And P2?

**tomas.b:** P2s just need an acknowledgement within four business hours, same as the incident policy.

**lena.k:** What counts as acknowledged?

**tomas.b:** Acknowledged means a person clicked acknowledge. Not that the task was opened, not that a bot commented on it.

**lena.k:** How should people be told?

**tomas.b:** Not email alone. Email is not reliable for this. A customer once marked our notifications as spam, and Relay stopped emailing that address for thirty days. Nobody noticed until they complained.

**lena.k:** Anything else about the notification itself?

**tomas.b:** When an escalation fires, the person needs to see why: which rule fired, which step, and when the clock started. Otherwise they argue with the rule instead of fixing the problem.

**lena.k:** The triage model already suggests priorities. Should that drive escalation?

**tomas.b:** I'd love that. If the model says P1, escalate straight away. Waiting for a person to confirm wastes the first ten minutes.

**lena.k:** How would you measure success?

**tomas.b:** Time to acknowledge, for P1s. I'd have to look up what ours is today. And escalations should work in a timely manner, obviously.

**lena.k:** Who uses the rule screens?

**tomas.b:** My leads. Two people on my team use screen readers, so whatever you build has to work from the keyboard.

**lena.k:** What would worry you once it's live?

**tomas.b:** Silence. If escalations stop firing, I want to know before a customer tells me.
