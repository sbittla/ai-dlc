Baseline sim-large:triage-v1 on 200 held-out tickets:
  single runs: run 1 81.5%, run 2 79.0%, run 3 86.0%
  all 600 calls: 82.2%, Wilson 95% 78.9% to 85.0% (treats calls as independent)
  resampling tickets, 1 run(s) each: 81.5%, 95% 76.0% to 86.5% (width 10.5 points)
  resampling tickets, 3 run(s) each: 82.2%, 95% 78.2% to 86.3% (width 8.2 points)

triage-v1.1 against triage-v1:
  unpaired: 82.2% (78.9% to 85.0%) vs 82.8% (79.6% to 85.6%)
  paired: difference +0.7 points, 95% -1.0 to +2.2; 2 worse, 0 better, McNemar p=0.500

Sample size (80% power, two-sided 5%), routed vs all-large discordance 9 of 200 = 4.5%:
  to detect a 2-point difference: 881 tickets
  to detect a 3-point difference: 391 tickets
  to detect a 5-point difference: 139 tickets
