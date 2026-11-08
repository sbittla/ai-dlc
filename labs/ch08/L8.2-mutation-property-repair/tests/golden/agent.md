# Mutation report: agent

Policy: `relay-mutation-v1` · threshold 90% per module, inclusive · operators ROR, AOR, CRP, LCR, NEG, RSD · 29 test cases

| Module | Line coverage | Mutants | Killed | Survived | Not covered | Equivalent | Score | Score with no equivalence claims |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `relay.escalation.rules` | 44 of 44 (100%) | 37 | 32 | 5 | 0 | 0 | 86.5% | 86.5% |
| `relay.escalation.evaluate` | 34 of 34 (100%) | 18 | 16 | 2 | 0 | 0 | 88.9% | 88.9% |
| `relay.escalation.hours` | 76 of 81 (94%) | 314 | 48 | 260 | 4 | 2 | 15.4% | 15.3% |
| **All** | 154 of 159 (97%) | 369 | 96 | 267 | 4 | 2 | 26.2% | 26.0% |

| Operator | Mutants | Killed |
| --- | ---: | ---: |
| AOR | 14 | 7 |
| CRP | 270 | 28 |
| LCR | 8 | 4 |
| NEG | 9 | 9 |
| ROR | 46 | 33 |
| RSD | 22 | 15 |

| Where the mutants are | Mutants | Killed | Score |
| --- | ---: | ---: | ---: |
| inside functions | 113 | 79 | 69.9% |
| module level (constants and data tables) | 256 | 17 | 6.6% |

## Mutants not killed, by line

| File | Line | Not killed | Example | Recorded as equivalent |
| --- | ---: | ---: | --- | --- |
| rules.py | 40 | 1 (survived) | RSD `raise -> pass` | no |
| rules.py | 46 | 1 (survived) | RSD `raise -> pass` | no |
| rules.py | 65 | 1 (survived) | ROR `<= -> <` | no |
| rules.py | 69 | 1 (survived) | ROR `<= -> <` | no |
| rules.py | 79 | 1 (survived) | RSD `raise -> pass` | no |
| evaluate.py | 39 | 1 (survived) | LCR `or -> and` | no |
| evaluate.py | 49 | 1 (survived) | ROR `>= -> >` | no |
| hours.py | 26 | 3 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 27 | 3 (survived) | CRP `2028 -> 2027` | no |
| hours.py | 35 | 25 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 36 | 31 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 37 | 31 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 38 | 24 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 39 | 8 (survived) | CRP `2027 -> 2026` | no |
| hours.py | 40 | 24 (survived) | CRP `2026 -> 2025` | no |
| hours.py | 41 | 8 (survived) | CRP `2027 -> 2026` | no |
| hours.py | 44 | 1 (survived) | CRP `True -> False` | yes: Zone becomes mutable; no code assigns to a Zone, so behaviour is unchanged |
| hours.py | 52 | 4 (survived) | CRP `11 -> 10` | no |
| hours.py | 53 | 4 (survived) | CRP `10 -> 11` | no |
| hours.py | 54 | 8 (survived) | CRP `8 -> 7` | no |
| hours.py | 55 | 8 (survived) | CRP `5 -> 4` | no |
| hours.py | 56 | 2 (survived) | CRP `0 -> -1` | no |
| hours.py | 57 | 4 (survived) | CRP `0 -> -1` | no |
| hours.py | 58 | 2 (survived) | CRP `120 -> 119` | no |
| hours.py | 59 | 7 (survived) | AOR `+ -> -` | no |
| hours.py | 60 | 4 (survived) | CRP `9 -> 10` | no |
| hours.py | 61 | 8 (survived) | CRP `10 -> 11` | no |
| hours.py | 62 | 8 (survived) | CRP `12 -> 11` | no |
| hours.py | 63 | 4 (survived) | CRP `13 -> 12` | no |
| hours.py | 64 | 14 (survived) | AOR `+ -> -` | no |
| hours.py | 65 | 4 (survived) | CRP `14 -> 13` | no |
| hours.py | 72 | 1 (not covered) | RSD `raise -> pass` | no |
| hours.py | 73 | 2 (survived) | ROR `< -> <=` | no |
| hours.py | 77 | 2 (survived) | ROR `< -> <=` | no |
| hours.py | 94 | 1 (survived) | ROR `is not -> is` | no |
| hours.py | 95 | 1 (survived) | AOR `- -> +` | no |
| hours.py | 99 | 1 (not covered) | AOR `- -> +` | no |
| hours.py | 104 | 4 (survived) | AOR `+ -> -` | no |
| hours.py | 114 | 1 (survived) | ROR `>= -> >` | no |
| hours.py | 117 | 1 (survived) | LCR `or -> and` | no |
| hours.py | 126 | 1 (survived) | AOR `+ -> -` | no |
| hours.py | 140 | 1 (survived) | RSD `raise -> pass` | no |
| hours.py | 141 | 4 (survived) | LCR `or -> and` | no |
| hours.py | 142 | 1 (not covered) | RSD `raise -> pass` | no |
| hours.py | 144 | 1 (not covered) | RSD `raise -> pass` | no |
| hours.py | 152 | 3 (survived) | LCR `and -> or` | no |
| hours.py | 154 | 1 (survived) | ROR `< -> <=` | yes: When begin equals closes the extra branch subtracts a zero-length window, which changes nothing |
| hours.py | 156 | 1 (survived) | CRP `1 -> 2` | no |

gate: FAIL - relay.escalation.rules: 86.5% is below 90%; relay.escalation.evaluate: 88.9% is below 90%; relay.escalation.hours: 15.4% is below 90%
