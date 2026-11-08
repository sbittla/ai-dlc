Family split (as shipped): 0 families in both splits; 0 held-out tickets with a near-duplicate in dev
triage-v1 prompt: 0 held-out tickets found in it
triage-v3 prompt: 7 held-out tickets found in it: T080 (0.94), T104 (1.00), T106 (0.95), T111 (1.00), T113 (1.00), T114 (1.00), T202 (0.88)
  triage-v3 against triage-v1, all 200 held-out tickets: +4.5 points (+1.9 to +7.6)
  excluding the 7 leaked tickets (193 left): +3.8 points (+1.5 to +6.5)
Row split instead (generated tickets shuffled and cut at 60): 37 families in both splits; 47 of 200 held-out tickets have a near-duplicate in dev (family split: 0 of 200)
Router trained on the family split: held-out hard recall 88.4% (114 of 129; Wilson 95% 81.7% to 92.8%)
Router trained on row splits, seeds 1-30: held-out hard recall mean 95.5%, SD 3.1 points, range 88.3% to 100.0%; inflation over the family split +7.2 points on average
  held-out tickets with a near-duplicate in dev, across those row splits: mean 47.1, range 36 to 58 of 200
