# The incident's migration, replayed on synthetic production-shaped data

| Measure | Agent's migration (#2291) | Relay 4.22.0's migrate_legacy |
| --- | ---: | ---: |
| Users with a legacy preferences row (synthetic) | 829 | 829 |
| Opt-outs before (user and type pairs) | 1,403 | 1,403 |
| Rows in the new opt-out table | 1,214 | 1,403 |
| ... of which name a notification type or "all" | 1,084 | 1,403 |
| Opt-outs lost | 319 | 0 |
| Users who lost at least one opt-out | 130 | 0 |
| Spam marks before | 78 | 78 |
| Spam marks lost | 36 | 0 |
| Legacy table kept | no | yes |
| Events replayed (2026-12-08T15:04 to 2026-12-09T09:10 UTC) | 6,000 | 6,000 |
| Emails sent against a preference | 388 | 0 |
| Emails withheld that the legacy code would send | 0 | 0 |

migrate_legacy's own proof: 0 user(s) whose preferences would change.
