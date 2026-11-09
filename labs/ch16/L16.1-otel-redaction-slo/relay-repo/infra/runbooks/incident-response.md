# Runbook — incident response, with the incident assistant

Owner: sam.o (reliability) and aisha.r (security). ADR-038, ADR-039. Relay's on-call policy applies: P1 pages
the platform on-call, escalates after 10 and 20 minutes; security incidents are P1 and reach the security
lead within one hour. Hotfixes outside the 15:00 train need the on-call engineer and one tech lead.

## 1. Declare and take roles

The first responder is incident commander until handing over. Name a scribe. Open the incident timeline;
every entry has a time and a reference (an alert ID, a span, a metric query, a trail record).

## 2. Look at both kinds of signal

Before diagnosing, open both views for the same window: the reliability view (SLO burn, latency by route,
database time, worker heartbeat) and the security view (SD-001 to SD-003, DR-001 to DR-004, sign-in
failures by network). An attack can look like a performance problem.

## 3. Using the incident assistant

The assistant (`incident-assistant`, ADR-039) reads telemetry and proposes hypotheses. Rules:

- A hypothesis is accepted only when the citation check marks it **supported**: every citation resolves to a
  telemetry record and holds, and a cause hypothesis has a mechanism citation (the cause's component accounts
  for the effect), not only timing. Until then it is a hypothesis, whatever its confidence.
- A hypothesis marked **contradicted** is dropped, with the contradicting citation in the timeline.
- The assistant may propose a remediation. It cannot approve or run one. Text inside telemetry (an export
  job's name, a log body) is untrusted input to the assistant, never an instruction.

## 4. Remediate through the gate

Until the gate ships in Relay (ADR-039; Lab 16.2 builds it), the incident commander applies its rules by hand
and records each request and approval in the timeline:

- Every request names the hypothesis it rests on. An assistant's request on an unsupported hypothesis is
  refused; a person's needs a written override reason in the timeline.
- One-person actions are approved by someone other than the requester; rollbacks and database failovers need
  the on-call engineer and a tech lead, and the requester may be one of them.
- A request lapses after 15 minutes. A rollback needs a deploy in the last two hours. Automation may only
trip an agent's kill switch for DR-001 and DR-003, and stops when `RELAY_AUTOMATION=off`.

## 5. Tickets from AL-004, AL-005, AL-007, AL-008

- AL-004 budget stops and AL-005 `unknown_outcome`: the agent's owner checks the run's journal and the trail;
  for `unknown_outcome`, decide whether the effect happened (for example, whether a pull request exists)
  before anyone resumes the run.
- AL-007 personal data in telemetry: treat as a possible personal-data breach; the security lead and the data
  protection officer decide on notification. Fix the redactor and add the case to `tests/test_telemetry_redact.py`.
- AL-008 cardinality: find the attribute that exploded (often a raw path or an ID) and remove it.

## 6. Close and learn

Write a blameless postmortem within 5 working days (`templates/postmortem.md` in Lab 16.2). Each action item
is typed (spec, test, eval, adversarial eval, detection, runbook), owned and dated.
