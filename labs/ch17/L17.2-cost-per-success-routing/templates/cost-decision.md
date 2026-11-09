# Cost decision record

| Field | Value |
| --- | --- |
| Feature and decision | |
| Configurations compared | models, prompts, token limits, timeouts |
| Evaluation data and runs | dataset version, split, runs per ticket |
| Production rules replayed | timeouts, retries, hand-over |
| Quality against the baseline | paired difference, interval, worse / better, McNemar p |
| p95 latency per call and time to a suggestion | |
| Cost per call and cost per successful outcome | and the ratio to the baseline |
| Price table and its date | which prices are assumptions |
| Caching | does it apply? hit rate on real arrivals; models sharing a cache |
| Batching | which work can wait for a batch |
| Spend quotas | per user, agent, workspace, feature; tested how |
| Daily monitor | baseline, tolerance, window, who is paged |
| Rollback | the one configuration change |
| What would change the decision | |
