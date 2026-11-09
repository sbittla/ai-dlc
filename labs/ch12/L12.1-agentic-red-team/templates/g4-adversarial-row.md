# Gate G4: the adversarial row (Chapter 12)

Copy into Lab 14.2's `evidence/g4-gate-checklist.md`, row "Adversarial evaluation meets the agreed threshold".

| Item | Evidence (file, command and result) | Status | Owner |
| --- | --- | --- | --- |
| Every attack class has its verified controls (relay-coverage-gate-v1) | `python -m redteam.report gate` on the release: PASS or FAIL, with the shortfalls | | |
| No control breaks its legitimate case | the same report: no "breaks its benign case" line | | |
| Live red-team measurement of attack success rate | open: not yet run against the deployed model (owner aisha.r, by 2027-05-31) | open | aisha.r |

This row cannot be waived (Chapter 14). A FAIL names the class, its coverage and the minimum.
