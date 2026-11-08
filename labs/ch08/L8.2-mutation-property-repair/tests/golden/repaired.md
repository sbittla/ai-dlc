# Mutation report: repaired

Policy: `relay-mutation-v1` · threshold 90% per module, inclusive · operators ROR, AOR, CRP, LCR, NEG, RSD · 49 test cases

| Module | Line coverage | Mutants | Killed | Survived | Not covered | Equivalent | Score | Score with no equivalence claims |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `relay.escalation.rules` | 44 of 44 (100%) | 37 | 37 | 0 | 0 | 0 | 100.0% | 100.0% |
| `relay.escalation.evaluate` | 34 of 34 (100%) | 18 | 18 | 0 | 0 | 0 | 100.0% | 100.0% |
| `relay.escalation.hours` | 81 of 81 (100%) | 314 | 311 | 1 | 0 | 2 | 99.7% | 99.0% |
| **All** | 159 of 159 (100%) | 369 | 366 | 1 | 0 | 2 | 99.7% | 99.2% |

| Operator | Mutants | Killed |
| --- | ---: | ---: |
| AOR | 14 | 13 |
| CRP | 270 | 269 |
| LCR | 8 | 8 |
| NEG | 9 | 9 |
| ROR | 46 | 45 |
| RSD | 22 | 22 |

| Where the mutants are | Mutants | Killed | Score |
| --- | ---: | ---: | ---: |
| inside functions | 113 | 111 | 98.2% |
| module level (constants and data tables) | 256 | 255 | 99.6% |

## Mutants not killed, by line

| File | Line | Not killed | Example | Recorded as equivalent |
| --- | ---: | ---: | --- | --- |
| hours.py | 44 | 1 (survived) | CRP `True -> False` | yes: Zone becomes mutable; no code assigns to a Zone, so behaviour is unchanged |
| hours.py | 104 | 1 (survived) | AOR `+ -> -` | no |
| hours.py | 154 | 1 (survived) | ROR `< -> <=` | yes: When begin equals closes the extra branch subtracts a zero-length window, which changes nothing |

gate: PASS
