# The opening incident, replayed

| Measure | Result |
| --- | ---: |
| Agent's tests passing on the agent's code | 14 of 14 |
| Line coverage of the agent's `delivery.py` by its tests | 31 of 35 (88.6%) |
| Line coverage of the agent's `hours.py` by its tests | 49 of 81 (60.5%) |
| Oracle findings on the agent's tests (blocking) | 6 (4) |
| Approved tests failing on the agent's code | 12 of 31 |
| Approved tests failing on the reference code | 0 of 31 |

## Oracle findings on the agent's tests

| Code | Test | Line | Finding |
| --- | --- | ---: | --- |
| OI01 | `test_ESC_AC15_signature_matches` | 58 | expected value computed by the code under test: sign(body, SECRET) == sign(event_body(event()), SECRET) |
| OI03 | `test_signature_format` | 62 | assertion checks only that a result is truthy, present or non-empty: sign(event_body(event()), SECRET).startswith('sha256=') |
| OI01 | `test_business_hours_inside_the_window` | 81 | expected value computed by the code under test: add_business_minutes(start, 60, HOURS) == expected |
| OI01 | `test_business_hours_before_opening` | 87 | expected value computed by the code under test: add_business_minutes(start, 60, HOURS) == opens + timedelta(minutes=60) |
| OI03 | `test_business_hours_result_exists` | 91 | assertion checks only that a result is truthy, present or non-empty: add_business_minutes(datetime(2026, 11, 27, 21, tzinfo=UTC), 240, HOURS) is not None |
| OI02 | `test_rendering_works` | 94 | test asserts nothing: no assert and no pytest.raises |

## Approved tests that fail on the agent's code

| Test file | Test | Checks |
| --- | --- | --- |
| test_escalation_delivery.py | `test_ESC_AC15_the_signed_bytes_are_the_bytes_sent` | ESC-AC15 |
| test_escalation_delivery.py | `test_ESC_AC15_two_targets_get_two_emails_and_one_signed_event` | ESC-AC15 |
| test_escalation_delivery.py | `test_ESC_AC27_no_part_of_the_title_in_emails_or_the_webhook_and_both_carry_the_link` | ESC-AC27 |
| test_escalation_delivery.py | `test_subjects_are_one_line_and_carry_no_number_from_the_title` | B5 |
| test_escalation_hours.py | `test_a_start_after_close_waits_for_the_next_day` | B3 |
| test_escalation_hours.py | `test_a_start_before_opening_waits_for_the_local_opening` | B3 |
| test_escalation_hours.py | `test_outside_the_covered_years_it_refuses_to_guess` | B3 |
| test_escalation_hours.py | `test_the_rule_zone_decides_not_berlin` | B3 |
| test_escalation_hours.py | `test_windows_follow_the_autumn_daylight_saving_change` | B3 |
| test_escalation_hours.py | `test_windows_follow_the_spring_daylight_saving_change` | B3 |
| test_escalation_policy.py | `test_SEC04_no_message_builder_receives_a_task` | SEC-04 |
| test_escalation_policy.py | `test_SEC06_events_are_signed_over_the_exact_body_and_the_secret_is_never_stored` | SEC-06 |

Failing approved tests by what they check: B3 6, B5 1, ESC-AC15 2, ESC-AC27 1, SEC-04 1, SEC-06 1
