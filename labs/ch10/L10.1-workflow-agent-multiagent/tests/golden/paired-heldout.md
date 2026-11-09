# Paired comparisons with the single agent (heldout split)

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.
Differences are candidate minus reference, in points, of the share of runs with the outcome; intervals resample families (cluster bootstrap); b and c count tasks by majority outcome (for wrong PRs, b counts tasks where only the reference opened a wrong PR by majority); p is exact McNemar.

| Candidate | Success difference | 95% interval | b | c | p | Cost per run | Gate | Wrong-PR difference | 95% interval | b | c | p |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: |
| Workflow | -5.9 | -10.0 to -2.6 | 3 | 0 | 0.250 | -32.7% | FAIL: a loss larger than the margin cannot be ruled out | +3.0 | +0.7 to +5.6 | 0 | 2 | 0.500 |
| Multi-agent | +1.1 | -2.2 to +4.1 | 2 | 2 | 1.000 | +71.5% | PASS: no clear change | -5.9 | -9.6 to -3.0 | 1 | 1 | 1.000 |
| Routed | +4.1 | +0.7 to +7.8 | 1 | 4 | 0.375 | +18.8% | PASS: improvement | -4.1 | -8.1 to -0.4 | 1 | 2 | 1.000 |

Routed and single agent disagree (by majority) on 5.6% of tasks. At that rate, detecting a 5-point difference with 80% power needs 173 tasks, and a 3-point difference 483.
