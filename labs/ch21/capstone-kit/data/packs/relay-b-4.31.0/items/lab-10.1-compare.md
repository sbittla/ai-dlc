# Four designs on the heldout split

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.

| Design | Tasks right (majority of 3 runs) | Wilson 95% | Runs right | Cost per run | Cost per success | Median s | p90 s | Model calls per run | Tool calls per run | Wrong PRs (runs) | Budget stops |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Workflow | 62 of 90 (68.9%) | 58.7% to 77.5% | 63.0% | $0.095 | $0.151 | 80 | 113 | 2.5 | 10.0 | 36 of 270 | 0 |
| Single agent | 65 of 90 (72.2%) | 62.2% to 80.4% | 68.9% | $0.142 | $0.206 | 101 | 137 | 11.4 | 10.3 | 28 of 270 | 6 |
| Multi-agent | 65 of 90 (72.2%) | 62.2% to 80.4% | 70.0% | $0.243 | $0.347 | 143 | 230 | 22.7 | 13.8 | 12 of 270 | 1 |
| Routed | 68 of 90 (75.6%) | 65.8% to 83.3% | 73.0% | $0.168 | $0.231 | 94 | 220 | 7.1 | 13.8 | 17 of 270 | 5 |

Routed runs that escalated to the agent: 91 of 270 (33.7%); of those, 30 succeeded and 5 stopped at the budget.
