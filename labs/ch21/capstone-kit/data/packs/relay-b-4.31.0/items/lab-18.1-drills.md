| Drill | Fault | Job | Run | PRs | Worker outcomes | Verdict |
| --- | --- | --- | --- | ---: | --- | --- |
| F0 | none (baseline) | done | finished (pull request opened) | 1 | waiting, done, idle | pass |
| F1 | the worker dies after the code host created the pull request | done | finished (pull request opened) | 1 | waiting, crashed, done, idle | pass |
| F2 | the request is delivered twice, and the run lasts longer than the lease | done | finished (pull request opened) | 1 | waiting, done, idle | pass |
| F3 | the model provider times out on every call | dead (attempts_exhausted) | running | 0 | retry, idle, retry, idle, retry, idle, dead, idle | pass |
| F4 | the model provider answers 429 with Retry-After 30 s for 100 s, four jobs queued | done | finished (pull request opened) | 4 | retry x3, paused x12, retry, paused x12, waiting, done, waiting, done, waiting, done, waiting, done, idle | pass |
| F5 | the agent's code tries a shell command and the metadata address | done | handed_back (agent:tests_failed) | 0 | done, idle | pass |
| F6 | the monitor trips the helper's kill switch while its tests run | dead (revoked) | revoked (disabled) | 0 | dead, idle | pass |
| F7 | the requester cancels the job while its tests run | cancelled | stopped (cancelled) | 0 | cancelled, idle | pass |
| F8 | the job's payload has no task | dead (poison_payload) | - | 0 | dead, idle | pass |

Drills passed: 9 of 9.
F1: attempts 2; the ledger repeated the pull request call 1 time, and the code host's key returned the existing one.
F2: second delivery created a new job: False; a second worker polling during the 100 s test step got: idle (lease 120 s, extended between steps).
F3: retry delays 10.8 s, 23.8 s, 31.5 s; attempts 4.
F4: calls refused with 429: 4; worker passes paused by the breaker: 24; breaker: open -> half_open -> open -> half_open -> closed.
F5: sandbox refusals refused:process, refused:network.
F6: refused tool open_pull_request (revoked:disabled), 102 simulated seconds after the trip.

