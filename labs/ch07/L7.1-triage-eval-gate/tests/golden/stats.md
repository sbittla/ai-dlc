Baseline sim-large:triage-v1 on 200 held-out tickets:
  single runs: run 1 81.5%, run 2 79.0%, run 3 86.0%
  all 600 calls: 82.2%, Wilson 95% 78.9% to 85.0% (treats calls as independent)
  resampling tickets, 1 run(s) each: 81.5%, 95% 76.0% to 86.5% (width 10.5 points)
  resampling tickets, 3 run(s) each: 82.2%, 95% 78.2% to 86.3% (width 8.2 points)
  resampling families (46), 3 runs each: 82.2%, 95% 77.4% to 86.6% (width 9.1 points)

triage-v1.1 against triage-v1:
  unpaired: 82.2% (78.9% to 85.0%) vs 82.8% (79.6% to 85.6%)
  paired, resampling families: difference +0.7 points, 95% -1.2 to +2.3; 2 worse, 0 better, McNemar p=0.500
  paired, resampling tickets: 95% -1.0 to +2.2
triage-v2 against triage-v1: resampling families -15.7 to -2.4; resampling tickets -14.0 to -4.8

Sample size (80% power, two-sided 5%; valid only for differences smaller than the disagreement rate):
  at the routed system's disagreement rate, 9 of 200 = 4.5%:
    to detect a 2-point difference: 881 tickets
    to detect a 3-point difference: 391 tickets
    to detect a 4-point difference: 219 tickets
  at a disagreement rate of 10.0%:
    to detect a 2-point difference: 1960 tickets
    to detect a 3-point difference: 870 tickets
    to detect a 5-point difference: 312 tickets
