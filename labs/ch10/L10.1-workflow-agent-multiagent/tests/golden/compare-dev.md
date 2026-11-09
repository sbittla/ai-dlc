# Four designs on the dev split

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.

| Design | Tasks right (majority of 3 runs) | Wilson 95% | Runs right | Cost per run | Cost per success | Median s | p90 s | Model calls per run | Tool calls per run | Wrong PRs (runs) | Budget stops |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Workflow | 22 of 30 (73.3%) | 55.6% to 85.8% | 66.7% | $0.098 | $0.147 | 80 | 113 | 2.5 | 10.2 | 7 of 90 | 0 |
| Single agent | 27 of 30 (90.0%) | 74.4% to 96.5% | 77.8% | $0.147 | $0.189 | 103 | 152 | 11.9 | 10.8 | 6 of 90 | 1 |
| Multi-agent | 25 of 30 (83.3%) | 66.4% to 92.7% | 74.4% | $0.253 | $0.339 | 146 | 233 | 23.5 | 14.7 | 5 of 90 | 0 |
| Routed | 26 of 30 (86.7%) | 70.3% to 94.7% | 77.8% | $0.172 | $0.222 | 94 | 223 | 7.1 | 14.0 | 8 of 90 | 2 |
| Routed without its review step (dev only) | 26 of 30 (86.7%) | 70.3% to 94.7% | 77.8% | $0.143 | $0.184 | 80 | 217 | 5.7 | 13.4 | 11 of 90 | 1 |

Routed runs that escalated to the agent: 27 of 90 (30.0%); of those, 12 succeeded and 2 stopped at the budget.
