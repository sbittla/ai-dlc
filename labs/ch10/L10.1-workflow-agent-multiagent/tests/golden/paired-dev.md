# Paired comparisons with the single agent (dev split)

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.
Differences are candidate minus reference, in points, of the share of runs with the outcome; intervals resample families (cluster bootstrap); b and c count tasks by majority outcome (for wrong PRs, b counts tasks where only the reference opened a wrong PR by majority); p is exact McNemar.

| Candidate | Success difference | 95% interval | b | c | p | Cost per run | Gate | Wrong-PR difference | 95% interval | b | c | p |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: |
| Workflow | -11.1 | -27.8 to +0.0 | 5 | 0 | 0.062 | -33.3% | FAIL: a loss larger than the margin cannot be ruled out | +1.1 | +0.0 to +3.3 | 0 | 0 | 1.000 |
| Multi-agent | -3.3 | -10.0 to +0.0 | 2 | 0 | 0.500 | +71.6% | FAIL: a loss larger than the margin cannot be ruled out | -1.1 | -4.4 to +2.2 | 0 | 0 | 1.000 |
| Routed | +0.0 | -6.7 to +5.6 | 2 | 1 | 1.000 | +17.0% | FAIL: a loss larger than the margin cannot be ruled out | +2.2 | -2.2 to +7.8 | 0 | 0 | 1.000 |

Routed and single agent disagree (by majority) on 10.0% of tasks. At that rate, detecting a 5-point difference with 80% power needs 312 tasks, and a 3-point difference 870.
