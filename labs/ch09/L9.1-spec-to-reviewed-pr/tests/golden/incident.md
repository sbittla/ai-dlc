# Pull request #2291: Modernize notifications: package, new schema, tests

| Measure | Value |
| --- | ---: |
| Files changed | 30 |
| Lines added | 3,641 |
| Lines removed | 426 |
| Changed lines in all | 4,067 |
| Changed lines outside tests/ | 2,602 |
| Commits | 1 |
| Existing test files changed | 6 |
| Review time (minutes) | 10 |
| Changed lines per minute of review | 407 |
| Blocking findings | 4 |
| Warnings | 1 |

## Findings

| Code | Blocking | Finding |
| --- | --- | --- |
| PR01 | yes | 2602 changed lines outside tests/ and 4067 in all; the limits are 200 and 400 |
| PR02 | yes | 6 existing test file(s) changed in a commit that changes code: tests/test_api.py, tests/test_digests.py, tests/test_mailer.py, tests/test_notifications.py, tests/test_settings_page.py, tests/test_unsubscribe.py |
| PR03 | yes | code changes with no tests-only commit before them |
| PR04 | yes | migration without a migration test: migrations/0042_notification_schema.py |
| PR08 | no | reviewed at 24,402 changed lines per hour; the guide is at most 500 |
