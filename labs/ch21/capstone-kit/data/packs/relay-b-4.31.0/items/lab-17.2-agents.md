# Chapter 10's designs: cost per success, the cache-write surcharge and recalibrated budgets

Held-out runs from Lab 10.1 (simulated sim-large; prices as of 2027-01-12). Surcharge: every uncached input token of a caching run written at 1.25 times the input price (assumption).

| Design | Runs | Successes | Cost per run | Cost per success | With surcharge | With no caching | Budget (Ch10) | Recalibrated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| workflow | 270 | 170 | $0.095 | $0.151 | $0.161 | $0.189 | $0.30 | $0.30 |
| single | 270 | 186 | $0.142 | $0.206 | $0.225 | $0.718 | $0.40 | $0.45 |
| multi | 270 | 189 | $0.243 | $0.347 | $0.386 | $0.736 | $0.65 | $0.70 |
| routed | 270 | 197 | $0.168 | $0.231 | $0.249 | $0.432 | $0.55 | $0.60 |

Recalibrated: 1.5 times the 95th percentile of successful dev runs' cost with the surcharge, rounded up to $0.05, as Lab 10.1 set its budgets.
