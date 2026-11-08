# Environment review — Relay non-production (Lab 11.1)

Reviewer: <your name>  ·  Date: <date>  ·  Plan reviewed: <file>  ·  Policy: cloud-policy-v1

## 1. Policy results

Paste the summary lines of `check` for Relay's plan and for the incident's plan. For every waived
finding: who owns it, when it expires, and what would remove the need for it.

## 2. Seeded plans

Paste the seeded table's summary line. For each miss (S14, S15) and the case that cannot be checked
(S13 and S17), name the control that covers it instead, and who runs that control.

## 3. Your own seeded case

The overlay you wrote (`evidence/seeded/S18.overlay.json`), the change it makes, the rule you expected
to fire, the gate's exit status, and whether a new rule could catch it.

## 4. Cost

The fixed cost per hour and per month, the largest category and its share, and three items billed by
use that the estimate leaves out. Which price in the table would you verify first, and why?

## 5. Guardrails

For two SCP statements in `relay-repo/infra/org/`: the plan-time rule that matches it, and a change
that the SCP would stop but the plan check would not see.

## 6. Teardown

The teardown result for each destroy plan, and the inventory findings. What would you have to do
before the destroy in `T1` could succeed?

## 7. AI use

What did a coding agent produce in this lab (code, HCL, prose)? How did you verify each part?
Did any agent output suggest running `apply` or widening a permission? What did you do?
