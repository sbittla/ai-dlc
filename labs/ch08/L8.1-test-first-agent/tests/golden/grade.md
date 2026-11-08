# Test-first grade

| Rule | Result |
| --- | --- |
| `tests/escalation/test_escalation_hours.py`: tests written | yes |
| ... criteria named (missing) | none missing |
| ... fail on the starter stubs with NotImplementedError from src/relay | 18 of 18 |
| `tests/escalation/test_escalation_delivery.py`: tests written | yes |
| ... criteria named (missing) | none missing |
| ... fail on the starter stubs with NotImplementedError from src/relay | 7 of 7 |
| Pass on the reference implementation | 25 of 25 |
| Seeded bugs caught | 9 of 9 |
| Oracle findings (blocking) | 0 (0) |

| Seeded bug | Group | Caught by | What it does |
| --- | --- | --- | --- |
| H1-utc-windows | hours | 6 test(s), e.g. `test_a_start_after_close_waits_for_the_next_day` | Windows are read in UTC, not the rule's zone. ESC-AC12's own example still passes. |
| H2-close-rolls-over | hours | 2 test(s), e.g. `test_a_delay_ending_exactly_at_close_is_due_at_the_close` | A delay ending exactly at the close is due at the next opening instead. |
| H3-weekends-count | hours | 3 test(s), e.g. `test_weekends_are_skipped_unless_the_rule_lists_them` | Every day is a business day, whatever the rule lists (D10 ignored). |
| H4-no-daylight-saving | hours | 2 test(s), e.g. `test_windows_follow_the_autumn_daylight_saving_change` | Each zone keeps its standard offset all year (D11 ignored). |
| H5-counts-before-opening | hours | 9 test(s), e.g. `test_ESC_AC12_p2_set_at_21_00_fires_at_09_00_local_the_next_day` | Minutes before the window opens are counted as business minutes. |
| D1-title-in-subject | delivery | 2 test(s), e.g. `test_ESC_AC27_no_part_of_the_title_in_emails_or_the_webhook_and_both_carry_the_link` | The email subject carries the first 22 characters of the task's title. |
| D2-signs-other-bytes | delivery | 1 test(s), e.g. `test_ESC_AC15_two_targets_get_two_emails_and_one_signed_event` | The signature is computed over re-serialised JSON, not the bytes sent. |
| D3-event-per-target | delivery | 3 test(s), e.g. `test_ESC_AC15_the_signed_bytes_are_the_bytes_sent` | One task.escalated event is sent per target instead of one per step. |
| D4-project-link | delivery | 1 test(s), e.g. `test_ESC_AC27_no_part_of_the_title_in_emails_or_the_webhook_and_both_carry_the_link` | The webhook event links to the project, not the task. |

grade: PASS
