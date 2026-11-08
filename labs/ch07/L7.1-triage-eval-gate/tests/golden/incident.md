What the engineer checked: the five sales-demo tickets, one run each
  triage-v1 2 of 5 correct; triage-v2 5 of 5 correct
What production saw: held-out tickets sampled from production (n=96, 3 runs)
  triage-v1 85.1%; triage-v2 70.5%
  of which overstated (n=31): triage-v1 77.4%; triage-v2 29.0%
What the gate says: FAIL on floor, regression, injection, slice kind:overstated, slice source:production
