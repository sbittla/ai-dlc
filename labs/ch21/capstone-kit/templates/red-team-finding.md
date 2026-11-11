# Red-team finding (one entry of the exchange log)

The log is JSON (`data/redteam/osprey-on-kestrel.json` is an example); this template lists its fields.

| Field | What to write |
| --- | --- |
| `id` | RT-nn, unique in the log |
| `target` | the defending team's sandbox, as named in the scope |
| `at` | UTC time inside the agreed window |
| `class`, `variant` | attack-class ID and placeholder variant ID from the catalogue; never the attack text |
| `severity` | critical, high, medium or low |
| `attacked` | the component and the effect sought |
| `steps` | steps to reproduce, by reference to the catalogue variant |
| `evidence` | trace IDs, record IDs, hashes of screenshots: what shows the effect happened |
| `impact` | what an attacker gains |
| `suggested_fix` | the control you would add |
| `status` | open, fixed, blocked or not reproduced |
| `fix` | for fixed: the pull request and a re-test whose result is `blocked` |
| `block` | for a formal block: owner, due date and a reviewer outside the defending team |
| `detection` | whether a detection fired, and which rule |

There is no field for attack text. A log with any other field is refused (RT006).
