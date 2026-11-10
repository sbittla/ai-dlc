# Runbook — game days

Owner: sam.o and aisha.r together. A game day injects faults on purpose, with people on call as usual, to test
detection, diagnosis, runbooks and the remediation gate. Lab 16.2 replays Relay's first.

- Plan: two faults at most, one reliability and one security, with stated sizes, times and a stop condition.
  Name the faults' owners; they are not on call that day.
- Environment: non-production with synthetic load, never customer data. Freeze deploys for the window.
- Abort: any responder may end the game day; the fault owners remove the faults within 2 minutes.
- Identities: a security fault runs under a game-day agent identity registered for the day, never a real
  agent's credentials, and its kill switch is part of the test.
- Record: every alert, page, acknowledgement, hypothesis (with the citation check's verdict), approval and
  action, with times. Measure time to detect, to acknowledge and to mitigate per fault.
- Afterwards: a blameless postmortem within 5 working days, with typed action items.
