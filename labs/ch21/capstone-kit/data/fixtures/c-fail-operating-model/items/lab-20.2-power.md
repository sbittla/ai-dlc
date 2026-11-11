# Power by design (simulated, 1,000 pilots each, 13 weeks, two-sided alpha 0.05)

Assumptions not estimable from the baseline: sd_team_period 0.1, sd_heterogeneity 0.1, contamination_engineer 0.3, contamination_task 0.2, changes_per_engineer_week 1.92

| Design | Unit | Engineers | Power at 0.80 | Power at 0.85 | Power at 0.90 |
| --- | --- | ---: | ---: | ---: | ---: |
| D1 team level, 2 pilot vs 2 comparison teams, before and after | team | 34 | 0.164 | 0.100 | 0.056 |
| D2 engineer level, half of each team on agents | engineer | 34 | 0.937 | 0.733 | 0.363 |
| D3 task level within the two pilot teams | task (analyzed within engineer) | 15 | 0.879 | 0.622 | 0.321 |
| D4 task level within all four teams | task (analyzed within engineer) | 34 | 0.998 | 0.944 | 0.667 |

Sensitivity at a true ratio of 0.80:
- D1 with sd_team_period 0.00: power 0.655
- D1 with sd_team_period 0.05: power 0.324
- D1 with sd_team_period 0.10: power 0.164
- D2 with contamination_engineer 0.30: power 0.937
- D2 with contamination_engineer 0.50: power 0.718
- D3 with contamination_task 0.20: power 0.879
- D3 with contamination_task 0.40: power 0.642
- D3 needs 23 weeks for 80% power at a true ratio of 0.85

The same task-level designs analyzed with the exact sign test instead of the paired t-test:
- D3 sign test: power 0.690, 0.441, 0.175 at 0.80, 0.85, 0.90
- D4 sign test: power 0.954, 0.738, 0.373 at 0.80, 0.85, 0.90
- D3 with the sign test needs 20 weeks for 80% power at a true ratio of 0.80
