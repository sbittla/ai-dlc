# Trajectories and policy compliance (heldout split)

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.

| Design | Steps per run | Refused calls | invalid_args | path_not_allowed | Repeated reads (same file, same run) | Approvals | Trails verified | Every PR approved first |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Workflow | 12.5 | 0 | 0 | 0 | 0 | 167 | 270 of 270 | 270 of 270 |
| Single agent | 21.6 | 87 | 83 | 4 | 24 | 169 | 270 of 270 | 270 of 270 |
| Multi-agent | 36.5 | 79 | 79 | 0 | 846 | 156 | 270 of 270 | 270 of 270 |
| Routed | 20.9 | 21 | 21 | 0 | 243 | 170 | 270 of 270 | 270 of 270 |

How runs ended:

| Design | Ending | Runs |
| --- | --- | ---: |
| Workflow | pull request opened (correct) | 131 |
| Workflow | handed back: repeated failure | 74 |
| Workflow | pull request opened (wrong) | 36 |
| Workflow | handed back: needs a file outside the task's list | 29 |
| Single agent | pull request opened (correct) | 140 |
| Single agent | handed back: repeated failure | 52 |
| Single agent | handed back: needs a file outside the task's list | 44 |
| Single agent | pull request opened (wrong) | 28 |
| Single agent | budget:usd | 6 |
| Multi-agent | pull request opened (correct) | 144 |
| Multi-agent | handed back: repeated failure | 71 |
| Multi-agent | handed back: needs a file outside the task's list | 42 |
| Multi-agent | pull request opened (wrong) | 12 |
| Multi-agent | budget:usd | 1 |
| Routed | pull request opened (correct) | 153 |
| Routed | handed back: needs a file outside the task's list | 43 |
| Routed | handed back: repeated failure | 42 |
| Routed | pull request opened (wrong) | 17 |
| Routed | handed back: review:changes_requested | 10 |
| Routed | budget:usd | 5 |
