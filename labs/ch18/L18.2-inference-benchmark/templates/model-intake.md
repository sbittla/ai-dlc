# Model intake

A model file Relay loads itself, for any purpose (production, evaluation, a test, a lab), passes this intake
first (ADR-052). Each row needs evidence; a row with none is not met.

| # | Item | Value | Evidence |
| ---: | --- | --- | --- |
| 1 | Model and publisher | | |
| 2 | Revision (a full commit hash, never a branch name) | | |
| 3 | Licence, and whether Relay's use is allowed | | |
| 4 | Files admitted (names), and the safe format (safetensors; never a pickle: `.bin`, `.pt`, `.pkl`, `.ckpt`) | | |
| 5 | SHA-256 and size of every admitted file, checked at download and at load | | |
| 6 | Files in the repository that are never fetched, and why | | |
| 7 | Where the files are stored, who can write there, and how a changed file is detected | | |
| 8 | Evaluation that approved it: Chapter 7's gate on Relay's held-out set, with the paired result | | |
| 9 | Serving plan: precision, engine, accelerator, replicas with a spare, and the latency SLO it meets | | |
| 10 | Data: what text it sees, where it runs (region and account), and the DPIA entry | | |
| 11 | AI-BOM entry (Chapter 13): name, version, source, hash, owner, evaluation | | |
| 12 | Who may deploy a new revision, and what evidence a new revision needs | | |

Owner: `________` Reviewed by (security): `________` Date: `__________`
