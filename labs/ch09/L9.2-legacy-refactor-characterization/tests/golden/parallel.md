# Five worktrees, integrated in order (the agents are simulated)

Waves: {T1} then {T2, T3} then {T4} then {T5}
Integration order: T1, T2, T3, T4, T5
Predicted overlaps: T2 and T3 both touch src/relay/notify/legacy.py

| Step | PR | Files | Outside tests/ | In all | Three-way merges | Conflicts | Re-run | Decisions that differ | get_prefs differences (accepted) | Write sequences that differ | Shadow differences | Tests passed | Rollback |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| T1 | notify-1 | 5 | 74 | 368 | - | - | no | 0 | 0 (0) | 0 of 40 | 0 | 5 | revert (nothing calls the package yet) |
| T2 | notify-2 | 3 | 76 | 113 | - | - | no | 0 | 0 (0) | 0 of 40 | 0 | 11 | revert (behaviour identical) |
| T3 | notify-3 | 4 | 183 | 252 | src/relay/notify/legacy.py | src/relay/notify/legacy.py line 4; src/relay/notify/legacy.py line 8 | yes | 0 | 0 (0) | 0 of 40 | 0 | 16 | revert (the legacy table was never altered) |
| T4 | notify-4 | 3 | 100 | 198 | - | - | no | 0 | 63 (63) | 0 of 40 | 0 | 21 | RELAY_NOTIFY_READ_FROM=legacy, or revert |
| T5 | notify-5 | 2 | 61 | 61 | - | - | no | 0 | 63 (63) | 0 of 40 | 0 | 21 | RELAY_NOTIFY_READ_FROM=legacy (dual write until 2027-01-31) |

Characterization cases at every step: 5,019; write sequences: 40
Largest step in all: T1, 368 changed lines (74 outside tests/); most outside tests/: T3, 183
Integrated result equals Relay 4.22.0's notify package and tests: yes
