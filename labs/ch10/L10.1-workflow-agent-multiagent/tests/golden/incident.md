# The opening incident, replayed

Simulated: sim-large's behaviour is configured in data/simulator.json; prices are assumptions as of 2027-01-12.

| Configuration | Stopped by | Rounds | Model calls | Input tokens | Output tokens | Cost | Minutes | Largest prompt (tokens) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| As run: no budget, transcript hand-offs, approval as the only stop | GitHub Actions job limit (6 hours) | 152 | 608 | 448,606,120 | 292,290 | $1,800.27 | 359.9 | 1,000,000 |
| With 4.24.0's controls: dev-calibrated budget, repeated-failure stop, summary hand-offs | budget:usd | 3 | 11 | 120,660 | 6,060 | $0.604 | 2.9 | 31,200 |
| Repeated-failure stop and summary hand-offs, no budget | repeated_failure:review:R1 | 3 | 13 | 149,360 | 6,660 | $0.731 | 3.7 | 31,200 |

As run, by agent:

| Agent | Model calls | Cost |
| --- | ---: | ---: |
| planner | 1 | $0.028 |
| supervisor | 152 | $448.34 |
| coder | 152 | $451.66 |
| tester | 152 | $451.10 |
| reviewer | 151 | $449.14 |

Commits pushed by the coder: 152. Review comments posted: 151.
The shared transcript grew by 12,320 tokens a round; at the start of round 3 it was 37,940 tokens.
Round 1 cost $0.332; round 80 cost $15.90; the last complete round, 151, cost $16.04.
Mean input per call: 737,839 tokens; the window (1,000,000) was full from round 81.
Assumed prompt processing: 40,000 input tokens per second, chosen with the token sizes so the loop fills the six-hour limit. At half that rate the same loop completes 109 rounds (440 calls) and costs $1,126.66 before the limit.
