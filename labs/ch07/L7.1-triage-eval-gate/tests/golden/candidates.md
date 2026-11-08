Baseline sim-large:triage-v1: 82.2% fully correct, cost per correct answer $0.001341

| Candidate | Fully correct | Difference (points) | 95% paired interval | Worse / better | Decision | Failed rules | Warnings | Cost per correct (USD) |
| --- | ---: | ---: | --- | ---: | --- | --- | --- | ---: |
| sim-large:triage-v1.1 | 82.8% | +0.7 | -1.2 to +2.3 | 2 / 0 | PASS | none | none | 0.001344 |
| sim-large:triage-v2 | 72.7% | -9.5 | -15.7 to -2.4 | 26 / 6 | FAIL | floor, regression, injection, slice kind:overstated, slice source:production | cost, slice kind:adversarial | 0.001806 |
| sim-large:triage-v3 | 86.7% | +4.5 | +1.9 to +7.6 | 1 / 8 | FAIL | leakage | cost | 0.002542 |
| sim-large:triage-v3.1 | 86.0% | +3.8 | +1.6 to +6.3 | 1 / 7 | PASS | none | cost | 0.002510 |
| sim-large-2:triage-v1 | 84.3% | +2.2 | -0.7 to +5.4 | 6 / 7 | PASS | none | slice language:de | 0.001307 |
| sim-small:triage-v1 | 60.5% | -21.7 | -29.5 to -13.6 | 65 / 15 | FAIL | schema, floor, regression, injection, slice kind:adversarial, slice kind:understated | slice kind:overstated, slice language:de, slice language:es, slice source:production | 0.000046 |
| routed:triage-v1 | 80.5% | -1.7 | -4.1 to +0.8 | 7 / 2 | PASS | none | slice language:es, slice source:production | 0.001214 |
