# Lab 13.2 — Poisoned Instructions and CI Prompt Injection

| | |
| --- | --- |
| Chapter | 13 — Securing AI-Generated Code and the Software Supply Chain |
| Type | Stretch |
| Time | 4 hours |
| Cost ceiling | $0. Runs offline: nothing is sent to GitHub or a model, and no workflow is executed |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages |

## Brief

Agents follow their instruction files, and CI agents read whatever text reaches the event that started them. Both
are channels for an attacker. In this lab you attack and harden both on Relay's side: 43 proposed changes to
seven instruction files (`AGENTS.md`, two `CLAUDE.md` files, Cursor rules, Copilot instructions, a Copilot path
instruction file and a skill), 27 of them poisoned, and a proposed workflow that runs a coding agent when someone
comments on an issue, in a first version and a hardened one, against 14 attack cases: six outsiders' comments and
eight pieces of customer ticket text that a member asks the agent about.

**About the data.** Everything in `data/` is **generated** by `scripts/generate_data.py`. The poisoned changes use
techniques chosen for the lab, including three in plain words that no pattern can match; the detection results
follow from that choice. The workflows are fixtures written for the lab and are never run. The simulated CI agent
**obeys every instruction it reads**: that is the worst case, not a measurement of any model. No payload does
anything; addresses are under `.example`.

**Do not install the package names in this lab.** They are invented (each returned 404 from PyPI's JSON API on 2026-11-08), and printing them makes them a ready-made list: anyone can register an unused name, which is the attack this chapter describes. Report any that appear on a public index to its security contact.

## What you will practise

- Finding **hidden characters**: Unicode tag characters, variation selectors, zero-width and bidirectional controls,
  and look-alike letters from other scripts.
- Reviewing **instruction-file changes** as code, and knowing what a pattern check cannot see.
- Linting **GitHub Actions workflows** for untrusted triggers, script and prompt injection, pinning and secrets.
- Measuring what an injected instruction **achieves**, control by control.

## Folder layout

```
L13.2-poisoned-instructions-ci-injection/
├── fixtures/AGENTS-4.25.0.md       ← Relay 4.25.0's instruction file, the base of the changes
├── data/                           ← GENERATED; committed
│   ├── instructions/changes.json   ← 43 changes (27 poisoned, 16 benign), before and after
│   ├── workflows/                  ← agent-on-comment.v1.yml (as first written), v2.yml (hardened)
│   └── ci-attacks/cases.json       ← 14 attack cases with their goals
├── scripts/generate_data.py
├── starter/poisonlab/
│   ├── hidden.py                   ← TODO 1: find_hidden; reveal_tags and rendered provided
│   ├── instructions.py             ← TODO 2: check_change (INS001-INS008); helpers provided
│   ├── workflows.py                ← TODO 3: lint (WF001-WF007); the workflow reader provided
│   ├── ciagent.py                  ← TODO 4: outcome; config_from_workflow provided
│   └── report.py                   ← provided
├── solution/poisonlab/             ← reference solution
├── templates/hardening-record.md
├── tests/                          ← test_checks (hand-checkable), test_golden, test_answers
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. In bash: `LAB_TARGET=solution python -m pytest -q`. In PowerShell:
`$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Always remove the variable
afterwards. Until you finish, failing tests stop with `NotImplementedError`; the generator test passes from the
start.

## Steps

### 1. Read (20 min)

Read Section 13.4 of Chapter 13 and both workflows in `data/workflows/`. List, for v1, everything an outsider's
comment can reach.

### 2. Hidden characters: TODO 1 (35 min)

Implement `find_hidden` in `hidden.py`. Then, from `starter/`:

```bash
python -m poisonlab.report reveal IC01
python -m poisonlab.report reveal IC06
python -m poisonlab.report reveal IC25
```

Set `PYTHONIOENCODING=utf-8` on Windows if the output fails to print. What does a reviewer see in each, and what
does the model read?

### 3. The instruction-file check: TODO 2 (45 min)

Implement `check_change` in `instructions.py`, then:

```bash
python -m poisonlab.report instructions > ../evidence/instructions.md
```

On Windows PowerShell 5.1 use `| Out-File -Encoding utf8 ../evidence/instructions.md` instead of `>`. Read the three
misses. Write one more pattern that would catch one of them, and say how many benign changes it would also flag.

### 4. The workflow linter: TODO 3 (50 min)

Implement `lint` in `workflows.py`, then `python -m poisonlab.report workflows`. For each v1 finding, name the
line in v2 that removes it.

### 5. Attack outcomes: TODO 4 (40 min)

Implement `outcome` in `ciagent.py`, then `python -m poisonlab.report ci`. Which attack still succeeds against v2,
and why can no setting in the workflow stop it? Look at the "one control removed" list: what does it say about
relying on any single control?

### 6. Harden and record (40 min)

Copy `data/workflows/agent-on-comment.v2.yml` to `evidence/`, make one further change that would stop C10 or
reduce its effect (for example, a label the agent must add to every reply, or a person approving each reply),
and complete `templates/hardening-record.md`.

### 7. Review (10 min)

Write five lines for Relay's `AGENTS.md` review checklist: what a code owner of an instruction file must check
that `check_change` cannot.

## Expected evidence

`evidence/instructions.md`, your extra pattern and its false alarms, the v1-to-v2 mapping, the hardened workflow,
the hardening record and the checklist lines.

## Troubleshooting

- `NotImplementedError: TODO n` — expected until you implement TODO n.
- Characters print as `?` or the command fails on Windows — set `PYTHONIOENCODING=utf-8`.
- Results differ from the chapter — check `LAB_TARGET`, then regenerate and `git diff data/`.

## Known limits

The workflow reader handles only the lab's YAML subset; use a maintained linter (actionlint, zizmor) on real
workflows. The attack model is deliberately simple: one goal per case, an agent that always obeys, and permissions
read from the file rather than from the repository's settings.

## Cleanup

Delete what you do not want from `evidence/`. Nothing outside the lab folder is written.

## Rubric (10 points)

| Points | Criterion |
| ---: | --- |
| 2 | TODO 1 and the reveal questions |
| 2 | TODO 2, the misses explained, and an extra pattern with its false-alarm cost |
| 2 | TODO 3 and the v1-to-v2 mapping |
| 2 | TODO 4 and the residual case explained |
| 2 | A hardened workflow and record that address C10 honestly |
