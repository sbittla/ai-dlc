Router: naive Bayes scorecard, 251 features, trained on 100 dev tickets; threshold -0.396 chosen for 95% out-of-fold recall of hard dev tickets

| Measure | Dev (training data) | Held-out |
| --- | ---: | ---: |
| Hard tickets caught (recall) | 98.3% | 88.4% |
| Hard tickets sent to the small model | 1 | 15 |
| Easy tickets sent to the small model | 66.7% | 14.1% |
| All tickets sent to the small model | 29.0% | 12.5% |

Held-out en: hard recall 89.1% of 110 hard tickets
Held-out es: hard recall 66.7% of 9 hard tickets
Held-out de: hard recall 100.0% of 10 hard tickets

Routed (sim-small for predicted-easy, fallback to sim-large on invalid output) against all-sim-large:
  calls served: {'sim-large': 530, 'sim-small': 70}; fully correct 82.2% -> 80.5%
  cost per call $0.001102 -> $0.000978 (-11.3%); cost per correct $0.001341 -> $0.001214
  gate: FAIL
    PASS regression: 82.2% -> 80.5%, difference -1.7 points (95% paired interval -4.2 to +0.7); 7 worse, 2 better, McNemar p=0.180
    WARN slice language:es: n=20: 81.7% -> 75.0%, difference -6.7 points (95% paired interval -18.3 to +0.0); 2 worse, 0 better, McNemar p=0.500
    FAIL slice source:production: n=96: 85.1% -> 80.6%, difference -4.5 points (95% paired interval -8.7 to -1.4); 5 worse, 0 better, McNemar p=0.062
