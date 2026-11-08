Policy `judge-policy-v1` on the heldout split

judge-v1, single grading: **KEEP HUMANS**
  ok   items: 120 human-labelled answers (minimum 100)
  FAIL kappa: kappa 0.58, 95% 0.43 to 0.72 (lower bound at least 0.60)
  FAIL human gap: humans agree at kappa 0.82; gap 0.23 (at most 0.15)
  FAIL false pass: 20 of 60 wrong answers passed (33.3%; at most 10%)
  FAIL verbosity: false passes: verbose 55.0% vs concise 22.5% (+32.5 points; at most 10)
  FAIL self-preference: false passes: own family 40.0% vs other 26.7% (+13.3 points; at most 10)

judge-v1, pairwise (both orders): **KEEP HUMANS**
  ok   pairs: 60 human-preferred pairs (minimum 50)
  FAIL swap: same answer chosen in both orders for 50.0% (at least 90%)
  FAIL accuracy: 80.0% agree with humans where both orders agree (at least 90%)

judge-v2, single grading: **MAY REPLACE HUMANS**
  ok   items: 120 human-labelled answers (minimum 100)
  ok   kappa: kappa 0.87, 95% 0.77 to 0.95 (lower bound at least 0.60)
  ok   human gap: humans agree at kappa 0.82; gap -0.05 (at most 0.15)
  ok   false pass: 3 of 60 wrong answers passed (5.0%; at most 10%)
  ok   verbosity: false passes: verbose 5.0% vs concise 5.0% (+0.0 points; at most 10)
  ok   self-preference: false passes: own family 10.0% vs other 0.0% (+10.0 points; at most 10)

judge-v2, pairwise (both orders): **KEEP HUMANS**
  ok   pairs: 60 human-preferred pairs (minimum 50)
  FAIL swap: same answer chosen in both orders for 76.7% (at least 90%)
  ok   accuracy: 95.7% agree with humans where both orders agree (at least 90%)

After approval: humans re-label a random 10% of judged items each release and the policy is re-checked on them; any change to the judge model, the judge prompt or the rubric repeats the calibration; adversarial and safety items are always labelled by humans.
