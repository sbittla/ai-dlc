# Mutation report: relay

Policy: `relay-mutation-v1` · threshold 90% per module, inclusive · operators ROR, AOR, CRP, LCR, NEG, RSD · 128 test cases

| Module | Line coverage | Mutants | Killed | Survived | Not covered | Equivalent | Score | Score with no equivalence claims |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `relay.escalation.rules` | 44 of 44 (100%) | 37 | 37 | 0 | 0 | 0 | 100.0% | 100.0% |
| `relay.escalation.evaluate` | 34 of 34 (100%) | 18 | 18 | 0 | 0 | 0 | 100.0% | 100.0% |
| `relay.escalation.hours` | 81 of 81 (100%) | 314 | 312 | 0 | 0 | 2 | 100.0% | 99.4% |
| `relay.escalation.delivery` | 32 of 32 (100%) | 8 | 7 | 0 | 0 | 1 | 100.0% | 87.5% |
| **All** | 191 of 191 (100%) | 377 | 374 | 0 | 0 | 3 | 100.0% | 99.2% |

| Operator | Mutants | Killed |
| --- | ---: | ---: |
| AOR | 15 | 15 |
| CRP | 274 | 272 |
| LCR | 9 | 9 |
| NEG | 9 | 9 |
| ROR | 47 | 46 |
| RSD | 23 | 23 |

| Where the mutants are | Mutants | Killed | Score |
| --- | ---: | ---: | ---: |
| inside functions | 121 | 119 | 98.3% |
| module level (constants and data tables) | 256 | 255 | 99.6% |

## Mutants not killed, by line

| File | Line | Not killed | Example | Recorded as equivalent |
| --- | ---: | ---: | --- | --- |
| hours.py | 44 | 1 (survived) | CRP `True -> False` | yes: Zone becomes mutable; no code assigns to a Zone, so behaviour is unchanged |
| hours.py | 154 | 1 (survived) | ROR `< -> <=` | yes: When begin equals closes the extra branch subtracts a zero-length window, which changes nothing |
| delivery.py | 72 | 1 (survived) | CRP `False -> True` | yes: Escaping non-ASCII characters changes the bytes but not the JSON; the spec fixes neither, and the signature covers the bytes sent |

gate: PASS
