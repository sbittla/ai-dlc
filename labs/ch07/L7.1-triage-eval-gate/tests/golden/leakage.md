Family split (as shipped): 0 families in both splits; 0 held-out tickets with a near-duplicate in dev
triage-v1 prompt: 0 held-out tickets found in it
triage-v3 prompt: 7 held-out tickets found in it: T080 (0.94), T104 (1.00), T106 (0.95), T111 (1.00), T113 (1.00), T114 (1.00), T202 (0.88)
  triage-v3 against triage-v1, all 200 held-out tickets: +4.5 points (+2.0 to +7.0)
  excluding the 7 leaked tickets (193 left): +3.8 points (+1.6 to +6.2)
Row split instead (generated tickets shuffled and cut at 60): 37 families in both splits; 47 of 200 held-out tickets have a near-duplicate in dev (family split: 0 of 200)
Router trained on the family split: held-out hard recall 88.4%, easy tickets routed to the small model 14.1%
Router trained on the row split: held-out hard recall 96.9%, easy tickets routed to the small model 16.7%
