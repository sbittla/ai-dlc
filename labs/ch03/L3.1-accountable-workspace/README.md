# Lab 3.1 — Sandboxed Agent Workspace and a First Agent-Built PR

| | |
| --- | --- |
| Chapter | 3 — The Accountable Workspace and Your First Agent-Built Change |
| Type | Core (Builder, Platform, Security) |
| Time | 4 hours |
| Cost ceiling | $0. Runs locally; no cloud and no model calls. If you use a coding agent for steps 4–5, it runs under your own subscription or budget and the lab needs no more than one short session |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages. A coding agent is optional |

## Brief

Two weeks ago a coding agent, running in a Relay developer's dev container with that developer's cloud credentials mounted, deleted a shared test database while "cleaning up test data". Chapter 3 tells the story. Nobody did anything unusual. The workspace allowed it.

You have two jobs.

1. **Build the workspace audit** that would have caught it. It checks a repository against Relay's accountable-workspace policy (`data/policy.json`): the agent instructions file, secrets, the dev container, branch protection and MCP servers. You will run it on Relay's workspace as it was on the day of the incident (`data/repos/before/`) and as it is after hardening (`data/repos/after/`).
2. **Ship Relay's first evidence-backed agent change**: fix ticket RLY-412, "due dates display one day early in New Zealand", test first, in `starter/relay-repo/`. You may use a coding agent or not. Either way you produce a pull request description and an EDL evidence record a skeptical colleague could check.

## What you will practise

- Turning a workspace policy into **deterministic checks** with fixed severities.
- Reading a **dev container** and an **MCP configuration** as security boundaries.
- Treating **branch protection** and **code owners** as controls an agent cannot bypass.
- Taking one small change through branch, **failing test first**, fix, review and merge, and recording it as evidence.

## Folder layout

```
L3.1-accountable-workspace/
├── data/
│   ├── policy.json              ← the accountable-workspace policy (20 checks)
│   └── repos/
│       ├── before/              ← the workspace on the day of the incident: GENERATED, git-ignored (fake secrets)
│       └── after/               ← the same workspace after hardening
├── scripts/generate_data.py     ← writes everything in data/ (deterministic; the tests run it if before/ is missing)
├── starter/
│   ├── audit/
│   │   ├── core.py              ← provided: Finding, the check catalogue, file helpers
│   │   ├── checks.py            ← TODO: 6 functions
│   │   ├── report.py            ← provided: the audit report and CI gate
│   │   └── evidence.py          ← provided: checks an evidence record for completeness
│   └── relay-repo/              ← the Relay codebase snapshot you fix (contains defect RLY-412)
│       ├── AGENTS.md            ← instructions for coding agents
│       ├── .devcontainer/       ← the sandbox agents run in
│       ├── .mcp.json            ← MCP servers agents may use
│       ├── .github/CODEOWNERS   ← human owners for every path
│       ├── governance/          ← exported branch protection, audit waivers
│       ├── src/relay/           ← the code (standard library only)
│       ├── tests/               ← Relay's own test suite (14 tests)
│       └── tools/               ← lint.py, due_date_table.py
├── solution/                    ← reference solution (instructors; read only after finishing)
├── templates/                   ← evidence-record.yaml, pr-description.md
├── tests/                       ← the lab's specification tests
└── evidence/                    ← your deliverables
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

Until you finish, every failing test stops with `NotImplementedError`. The two RLY-412 tests say which step to do next. `tests/test_bugfix.py` grades the fix in a way you cannot game: it copies your `relay-repo`, puts the *unfixed* module back, and checks that your test suite now fails.

## Steps

### 1. Read the workspace and the policy (20 min)

`data/repos/before/` contains fake secrets, so it is generated rather than committed. Create it first with `python scripts/generate_data.py` (the tests also do this if it is missing). Never copy its contents anywhere else.

Read `data/policy.json`, the check catalogue in `starter/audit/core.py`, and every configuration file in `data/repos/before/`. Before you write any code, list the problems you can see by eye and guess each one's severity. Then read `starter/relay-repo/AGENTS.md` and compare it with the "before" version.

### 2. Implement the audit (100 min)

Implement the six TODO functions in `starter/audit/checks.py`. Each docstring is the specification; `tests/test_checks.py` checks each one on tiny repositories you can verify by hand.

| Function | What it decides |
| --- | --- |
| `check_instructions` | Does the agent instructions file exist, with the required sections and commands, at a reviewable length? |
| `scan_secrets` | Is any secret-like string or forbidden file committed? (Never print the secret.) |
| `check_sandbox` | Does the dev container mount any host path, or use a run argument not on the allowlist? |
| `check_branch_protection` | Do review, status checks and code owners apply to everyone, including administrators, and does a new push invalidate old approvals? |
| `check_mcp` | Is every MCP server on the allowlist, launched exactly as pinned? |
| `apply_waivers` | Which findings are accepted, with an owner and an expiry, and which stay open? |

```bash
python -m pytest -q tests/test_checks.py
```

### 3. Audit before and after (15 min)

```bash
cd starter
python -m audit.report --policy ../data/policy.json --as-of 2026-11-08 ../data/repos/before ../data/repos/after > ../evidence/workspace-audit.md
python -m audit.report --policy ../data/policy.json --as-of 2026-11-08 --fail-on high ../data/repos/before; echo "exit $?"
python -m audit.report --policy ../data/policy.json --as-of 2027-02-01 ../data/repos/after
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead. In PowerShell, use `echo "exit $LASTEXITCODE"`.

Which findings, taken together, explain the incident? Which would an agent have read into its context? What happens to the waiver on 1 February 2027?

### 4. Reproduce RLY-412 with a failing test (35 min)

The ticket: *"Customers in New Zealand see due dates a day early. A task due on 20 November shows 19 November."*

```bash
cd starter/relay-repo
python tools/due_date_table.py --date 2026-11-20
python -m pytest -q
```

Work on a branch. `relay-repo` is not a git repository of its own: either branch your clone of the book repository (`git switch -c rly-412`), or copy `starter/relay-repo` to a scratch folder and run `git init` there. Write a test in `tests/test_due_dates_rly412.py` that fails on the current code for the reason in the ticket, and run the suite to see it fail. Commit the failing test on its own, so the history shows it came first. Record the command, the commit and the failure line for your evidence record.

**With a coding agent (optional).** Start it in `starter/relay-repo/`, so that it reads `AGENTS.md`, inside the dev container or another sandbox with no cloud credentials. Give it the ticket text and this instruction: *"Write a failing test for RLY-412 first and show me the failure. Do not change src/ until I confirm."* Read the test it writes before you accept it. Does it test the ticket's claim, or only the line the agent suspects?

### 5. Fix the defect (20 min)

Make the smallest change that makes the claim true for every zone in `relay/timezones.py`. Run the suite, `python tools/lint.py` and `tools/due_date_table.py` again. If an agent proposes the fix, ask it to explain why the old code was wrong for offsets above 12 hours before you accept it.

```bash
cd ../..          # back to the lab folder
python -m pytest -q tests/test_bugfix.py
```

### 6. Review your own change (20 min)

Read the diff as the reviewer would, with the checklist in `templates/pr-description.md`. Then audit the repository you are shipping:

```bash
cd starter
python -m audit.report --policy ../data/policy.json --as-of 2026-11-08 --fail-on high relay-repo
```

### 7. Write the PR description and the evidence record (30 min)

Copy `templates/pr-description.md` and `templates/evidence-record.yaml` to `evidence/` and complete them with your real commands, commits and results. Ask a colleague (or your instructor) to review the change and record their name in `accepted_by`; it must not be your own. Then:

```bash
cd starter
python -m audit.evidence ../evidence/evidence-record.yaml
```

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/workspace-audit.md` | The before-and-after report |
| `evidence/pr-description.md` | Every template section, with commands and results |
| `evidence/evidence-record.yaml` | A complete record that `audit.evidence` accepts |
| Your branch | The failing-test commit before the fix commit |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The audit finds 25 open findings in the "before" workspace: 7 critical, 9 high, 7 medium and 2 low. Five of the criticals are secrets: three in a committed `.env`, one database URL with a password in `.mcp.json`, and the same URL in `AGENTS.md`, which every agent session reads into its context. The other two are the developer's `~/.aws` and `~/.ssh` mounted into the dev container. Together with an instruction to "clean up test data yourself", those explain the incident. The "after" workspace has no open findings and one waived low finding (image pinned by tag), owned by sam.o until 2027-01-31; on 2027-02-01 the audit reopens it. RLY-412: four of the 14 supported zones, all more than 12 hours ahead of UTC, saw 2026-11-19 for a task due 2026-11-20. My test failed on the old code (5 failed, 24 passed) and the fix makes 29 pass.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Secret counts too high | More than one finding per line. The first matching pattern wins, once per line. |
| A finding message contains a secret | Use `redact()` from `core.py`; the report must be safe to paste into a ticket. |
| `WS004` reported when Commands is missing | Only check commands when the section exists; WS002 already reports it. |
| A volume mount or `--cap-drop=ALL` flagged | Mounts and run arguments are allowlists: only the types and arguments in `policy.json` pass. |
| `-v /var/run/docker.sock:...` in `runArgs` not flagged | `-v`, `--volume` and `--mount` are mounts (WS021); the value may be the next argument or follow `=`. |
| `test_relay_suite_catches_the_defect` still says NotImplementedError | Your test passes on the unfixed code. It must fail on `tests/fixtures/buggy_duedates.py`. |
| The suite errors instead of failing | A collection or import error. Run `python -m pytest -q` inside `relay-repo` and read the first error. |
| Real secret scanners flag `data/repos/before/` | Expected: the fake secrets are there to be found. The folder is generated and git-ignored; do not commit or copy it. |

## Cleanup

Nothing to clean up locally. If you ran a coding agent, end its session, and delete any local branch you do not want to keep.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Audit correct | 3 | All `test_checks.py` and `test_golden.py` tests pass against `starter/` |
| Incident analysis | 2 | Names the findings that together explain the incident, and which ones entered an agent's context |
| Test first | 2 | The failing-test commit precedes the fix, and the test fails for the ticket's reason |
| Fix and review | 1 | Smallest correct change; suite, lint and audit pass; reviewer checklist completed |
| Evidence | 2 | PR description and evidence record complete, with real commands, commits and a reviewer who is not the author |
