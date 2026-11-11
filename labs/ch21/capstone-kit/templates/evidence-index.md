# Evidence index (pack.json, explained)

`pack.json` is the evidence index. For each acceptance criterion it names the items that evidence it; for each
item it names the file, its SHA-256, its label (verified, modelled, deployed or open), its owner and the sources
it was produced from. Check it with `python -m capstone.report check <pack folder>` before every checkpoint.

| Criterion | Evidence items | Label of each | Who accepted it, and when |
| --- | --- | --- | --- |
| | | | |

Open items: each with an owner and a date. A limitation you state here is one the panel does not have to find.
