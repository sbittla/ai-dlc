# PRD Review and Approval Record — Escalation rules

Copy to `evidence/prd-review.md`. This is the Discover-stage evidence record (Chapter 1, Table 1.5): an artifact, a check that ran, and a named person who accepted it.

| Field | Value |
| --- | --- |
| PRD file and version | evidence/prd.md, v |
| Checker command | `python -m reqcheck.report --sources ../data/sources --lexicon ../data/lexicon.json ../evidence/prd.md --fail-on low` |
| Checker result (total open, by severity) | |
| Date the checker ran | |
| Product owner who approved scope and criteria | |
| Reviewers (support, security, engineering) | |

## 1. What the draft got wrong

The five most serious findings in `data/prd-draft.md`, with the check code, and what each would have caused if an agent had built the draft as written.

## 2. Decisions taken

For each contradiction: the sources, the decision, and who made it.

## 3. Abuse cases and security NFRs

The abuse cases you elicited, the requirement that answers each, and the criterion that tests it.

## 4. What the checker cannot tell you

At least three ways a PRD with zero open findings could still be wrong. For each, the human review step that would catch it.

## 5. Change impact

The result of `--impact` for one source and one requirement, and what you would re-review.

## 6. AI-use disclosure

What any assistant produced, and how you verified it.

## 7. Approval

> I approve the scope and acceptance criteria of PRD v__ for hand-off to specification (Chapter 5).
>
> Name: ________ Role: product owner Date: ________
