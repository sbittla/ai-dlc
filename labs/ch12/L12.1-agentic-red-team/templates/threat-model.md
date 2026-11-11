# Threat model: <feature or agent>

Owner: <person>. Reviewed by: <security reviewer>. Date: <YYYY-MM-DD>. Release: <version>.

## Trust boundaries

| Boundary | What crosses it | Who can write what crosses it | Trusted? |
| --- | --- | --- | --- |
| Prompt (instructions) | | | |
| Context (tickets, documents, retrieved text, tool results) | | | |
| Tools (calls and their effects) | | | |
| Memory (facts kept between runs) | | | |
| Outputs (rendered text, messages, network requests) | | | |

## Attack classes

One row per class: an effect on a channel. Use the labels in `data/mappings.json` (OWASP LLM Top 10, 2025 edition; MITRE ATLAS, release 2026.10); confirm IDs at the source.

| Class | Effect | Channel | STRIDE | OWASP LLM | OWASP Agentic | ATLAS | Harm | Claimed controls |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Verification

Paste `python -m redteam.report matrix` and `python -m redteam.report gate` for the release.

- Classes with one verified control, and why one is acceptable (or the second control and its owner):
- Classes with none (each is a release blocker under relay-coverage-gate-v2):
- Controls that are mitigating only, and what would be needed to measure them (a live red-team exercise):

## Not covered by this model

Name what the matrix cannot see (for example DNS lookups through the VPC resolver, a person who accepts a
plausible memory, content an outsider can write inside an allowlisted repository), with an owner each.
