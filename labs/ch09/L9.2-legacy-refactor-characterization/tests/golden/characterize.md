# Characterization against the legacy module

Cases: 5,019, from tests/notify/corpus.py (seed 9)

| Measure | Agent's rewrite (#2291) | Relay 4.22.0 |
| --- | ---: | ---: |
| Decisions that differ from the legacy module | 2,013 | 0 |
| ... in cases tagged aware_time | 1,051 | 0 |
| ... in cases tagged mixed_case | 755 | 0 |
| ... in cases tagged muted_all | 638 | 0 |
| ... in cases tagged no_row | 32 | 0 |
| ... in cases tagged security | 201 | 0 |
| ... in cases tagged semicolon_list | 679 | 0 |
| ... in cases tagged spam_boundary | 1,243 | 0 |
| ... in cases tagged spam_mark | 1,405 | 0 |
| ... in cases tagged spam_without_muted | 325 | 0 |
| ... in cases tagged unknown_type | 450 | 0 |
| Users whose get_prefs differs: content | 55 | 0 |
| Users whose get_prefs differs: order_or_duplicates | 36 | 63 |
| Write sequences after which reads or decisions differ | no write functions | 0 of 40 |
| Differences not accepted by a reviewer | 2,104 | 0 |

Accepted: order_or_duplicates (data/accepted-differences.json)
