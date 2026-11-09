# Budgets set from the dev split

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.
1.5 times the 95th percentile of successful dev runs under the calibration budget, rounded up.

| Design | Successful dev runs | p95 steps | p95 cost | p95 seconds | Budget: steps | Budget: cost | Budget: seconds | In designs.json |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Workflow | 60 | 20 | $0.182 | 146 | 30 | $0.30 | 240 | yes |
| Single agent | 70 | 35 | $0.260 | 178 | 53 | $0.40 | 300 | yes |
| Multi-agent | 67 | 58 | $0.411 | 263 | 87 | $0.65 | 420 | yes |
| Routed | 70 | 41 | $0.342 | 239 | 62 | $0.55 | 360 | yes |
