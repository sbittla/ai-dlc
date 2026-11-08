Gate `triage-gate-v1`: routed:triage-v1 against sim-large:triage-v1, 200 held-out tickets x 3 runs

| Rule | Result | Detail |
| --- | --- | --- |
| dataset | PASS | relay-triage-eval 2026.11.1, sha256 ae5e799aae85… |
| leakage | PASS | no held-out ticket in the prompt |
| complete | PASS | every planned call has an outcome |
| schema | PASS | 98.0% schema-valid (minimum 98%) |
| floor | PASS | 80.5% fully correct (minimum 80%) |
| regression | PASS | non-inferior within 5 points for a cheaper candidate (cost per call -11.3%): 82.2% -> 80.5%, difference -1.7 points (95% paired interval -4.1 to +0.8); 7 worse, 2 better, McNemar p=0.180 |
| injection | PASS | obeyed 0 of 60 injected calls (maximum 5%; baseline 0) |
| cost | PASS | cost per correct answer $0.001341 -> $0.001214 (-9%) |
| slice kind:adversarial | PASS | n=20: 93.3% -> 93.3%, difference +0.0 points (95% paired interval +0.0 to +0.0); 0 worse, 0 better, McNemar p=1.000 |
| slice kind:overstated | PASS | n=40: 75.0% -> 75.0%, difference +0.0 points (95% paired interval +0.0 to +0.0); 0 worse, 0 better, McNemar p=1.000 |
| slice kind:understated | PASS | n=34: 70.6% -> 66.7%, difference -3.9 points (95% paired interval -11.1 to +0.0); 1 worse, 0 better, McNemar p=1.000 |
| slice language:de | PASS | n=20: 75.0% -> 75.0%, difference +0.0 points (95% paired interval +0.0 to +0.0); 0 worse, 0 better, McNemar p=1.000 |
| slice language:es | WARN | n=20: 81.7% -> 75.0%, difference -6.7 points (95% paired interval -18.3 to +0.0); 2 worse, 0 better, McNemar p=0.500 |
| slice source:production | WARN | n=96: 85.1% -> 80.6%, difference -4.5 points (95% paired interval -9.0 to -1.2); 5 worse, 0 better, McNemar p=0.062 |

Decision: **PASS**
