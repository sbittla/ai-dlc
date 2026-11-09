# Performance claim

A performance number without these fields cannot be reproduced or compared. Fill in every one.

| Field | Value |
| --- | --- |
| Claim (one sentence) | |
| Code version and configuration | e.g. Relay 4.28.0, `SharedRateLimiter(block=10)` |
| Workload | name and version of `perf/workload.json`; rate; mix; callers |
| Open or closed schedule; seed | |
| Environment | CPU, logical CPUs, OS, Python, SQLite, disk, power, other load |
| Processes | service processes, worker, client threads |
| Warm-up discarded | |
| Steady-state duration per run | |
| Runs, and how configurations were ordered | |
| Percentiles reported and how computed | e.g. nearest rank on every steady-state request, from due time |
| Run-to-run spread | intervals, and how computed |
| Errors | |
| Budget and verdict | |
| What this does not show | network, load balancer, database engine, real model, ... |
| Machine-dependent numbers | which, and how a reader's may differ |
