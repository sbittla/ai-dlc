# PRD — Escalation rules

<!--
Copy this file to evidence/prd.md and complete it. The checker parses the Goals,
Decisions and Requirements sections and the header fields; everything else is for
people. Keep the field names exactly as written ("Source:", "Statement:", ...).

Rules the checker enforces (python -m reqcheck.report ... ../evidence/prd.md):
- Every requirement and goal has at least one Source line: <DOC-ID> | <quote copied
  word for word from data/sources/<DOC-ID>.md>, at least 5 words long.
- Statements use "must", "must not" and "can"; no "should", "may", "could".
- No vague terms (data/lexicon.json lists them).
- Every NFR has a number with a unit, a named standard, or a "must not".
- Every requirement has at least one criterion, in Given/When/Then form.
- A concept Relay 4.17.2 lacks (priority, acknowledgement, business hours, ...) is
  introduced by exactly one requirement ("Introduces:"), and every requirement that
  uses it lists that requirement under "Depends on:".
- Every NFR category in the lexicon is covered, including abuse cases.
- Status approved, Approved by = Product owner, Approved on = a date. An agent cannot approve.
-->

Version: 0.2
Status: draft
Product owner: lena.k
Approved by:
Approved on:
Drafted by: <you; name any assistant you used and what it produced>

## Problem

<Two or three sentences: what goes wrong today, for whom, and how you know. Cite sources.>

## Users

- <Who sets rules up, who receives escalations, who confirms priorities. Cite sources.>

## Scope

- In: <...>
- Out of version 1: <... and the decision that put it out>

## Constraints

- <Plan, platform and baseline-code constraints.>

## Risks

- <What could go wrong for customers or for Relay, including data exposure and abuse.>

## Open questions

- <Question. Owner: <name>.>

## Goals

### G1 — <outcome, not output>
Measure: <exact definition: what is counted, over which population and period, from which system>
Baseline: <the measured value, or how and when it will be measured>
Target: <number and date>
Source: <DOC-ID> | <verbatim quote>

## Decisions

### D1 — <the choice made>
Resolves: <which sources disagreed, and how>
Decision: <what was decided, and when it will be revisited>
Decided by: <the product owner>

## Requirements

### ESC-R01 — <short title>
Kind: functional
Goal: G1
Decision: D1
Source: <DOC-ID> | <verbatim quote>
Statement: <one paragraph using must / must not / can>
Value: <key> = <value>
Introduces: <concept, if this requirement creates it>
Depends on: <requirement ids>
Criteria:
- ESC-AC01: Given <state>, when <event>, then <observable result>.

### ESC-N01 — <short title>
Kind: nfr
Category: <security | abuse | privacy | accessibility | operability | cost | human-ai>
Goal: G1
Source: <DOC-ID> | <verbatim quote>
Statement: <a measurable threshold, a named standard, or a prohibition>
Criteria:
- ESC-AC02: Given <state>, when <event>, then <observable result>.
