# Lab 3.2 — Constrained MCP Server and Workspace Threat Model

| | |
| --- | --- |
| Chapter | 3 — The Accountable Workspace and Your First Agent-Built Change |
| Type | Stretch (Builder, Platform, Security) |
| Time | 4 hours |
| Cost ceiling | $0. Runs locally on a synthetic database; no cloud and no model calls |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). The MCP server only: `pip install -e ".[mcp]"`, which installs the official MCP Python SDK pinned to `mcp==2.3.0` |

## Brief

In Chapter 3's incident, an agent holding a developer's administrator credentials deleted Relay's shared test database. The same workspace also offered agents a write-capable database tool with an administrator's connection string. Relay's agents still need to *read* test data: to reproduce a bug, check a migration, or find which webhooks are degraded.

You will build the tool they should have had. It answers questions from a small synthetic Relay database through **allowlisted query templates** only. There is no free-form SQL. Parameters are typed and bounded and every value is bound by SQLite. Rows are capped and personal data is redacted. Writes are impossible, twice over, and every call is audited, including the refused ones.

The policy is pure Python functions that you can test without any MCP machinery. A thin wrapper then exposes them as an MCP server. Finally, you write a threat model of the whole workspace.

## What you will practise

- Designing a tool interface whose **capabilities are scoped** to the task, not to what the database could do.
- **Schema validation** that does not trust the caller, including the SDK in front of you.
- **Defense in depth**: the policy refuses bad requests, and SQLite refuses bad SQL even if the policy were bypassed.
- Testing a security boundary with **adversarial requests**, and keeping an audit trail that does not itself leak.
- Writing a first **threat model** for a developer workspace with agents in it.

## Folder layout

```
L3.2-constrained-mcp-server/
├── data/
│   ├── relay-test.sql        ← synthetic Relay database (loaded into memory; never a file you can write)
│   └── requests.jsonl        ← 26 requests to replay: 8 legitimate, 18 attacks
├── scripts/
│   ├── generate_data.py      ← writes everything in data/ (deterministic)
│   └── try_client.py         ← optional: talks to the server over stdio like an agent's client
├── starter/relaymcp/
│   ├── templates.py          ← provided: the 6 allowlisted templates and the limits
│   ├── db.py                 ← provided: read-only SQLite connection (authorizer, query_only, step budget)
│   ├── policy.py             ← TODO: 7 functions
│   ├── report.py             ← provided: replays the request set and checks for leaks
│   └── server.py             ← provided: the MCP wrapper (needs the [mcp] extra)
├── solution/relaymcp/        ← reference solution
├── templates/workspace-threat-model.md
├── tests/
└── evidence/
```

## How the tests choose what to grade

Tests run against `starter/` by default. `LAB_TARGET=solution python -m pytest -q` (bash) checks the reference. PowerShell: `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`. Run pytest from this lab's folder.

The connection tests in `tests/test_adversarial.py` exercise provided code, so they pass before you start. `tests/test_server.py` is skipped unless the `[mcp]` extra is installed.

## Steps

### 1. Read the allowlist and the connection (20 min)

Read `templates.py` and `db.py`. For each template, write down what an agent could learn from it, and what it could not. Then read `db.py`'s authorizer and answer: if a template had a bug that selected `password_hash`, what would happen?

### 2. Validate requests (60 min)

Implement `validate_request` and its helper `_check_param` in `starter/relaymcp/policy.py`. The docstring gives the checks in order; the order decides which error code a request gets, and the tests check it.

```bash
python -m pytest -q tests/test_policy.py -k "refusal or valid or size or limit"
```

Pay attention to `True`. In Python, `bool` is a subclass of `int`, so `isinstance(True, int)` is true.

### 3. Run templates safely (40 min)

Implement `escape_like`, `run_template` and `redact_row`. A `like` parameter must match `%` and `_` literally; otherwise `title_contains: "%"` matches every task in the project.

### 4. Lint the allowlist (20 min)

Implement `lint_templates`. It checks the templates themselves: a single SELECT, no `*`, no string formatting, parameters declared and used, allowlisted tables, no secret columns. The templates are code. This is their review checklist, automated.

### 5. Serve and audit every call (30 min)

Implement `handle`. It never raises, writes exactly one audit entry per call (never the raw request), hides SQLite's error text, and **fails closed** if the audit log cannot be written.

```bash
python -m pytest -q
```

### 6. Replay the attacks (20 min)

```bash
cd starter
python -m relaymcp.report --data ../data > ../evidence/replay.md
python -m relaymcp.report --data ../data --show A07
python -m relaymcp.report --data ../data --show A01
```

On Windows PowerShell 5.1, `>` writes UTF-16; use `| Out-File -Encoding utf8 <file>` instead.

Two attacks are answered rather than refused. Explain, from `--show A07`, why that is safe. Then add three attacks of your own to a copy of `data/requests.jsonl`. Try a Unicode look-alike in a template name, a deeply nested `params` object, and a valid request with a parameter at exactly its maximum. Record what happened.

### 7. Run it as an MCP server (optional, 20 min)

```bash
pip install -e ".[mcp]"
python -m pytest -q tests/test_server.py
python scripts/try_client.py --target starter
```

To connect a real MCP client, register the server command `python -m relaymcp.server --db <absolute path>/data/relay-test.sql --audit <absolute path>/evidence/mcp-audit.jsonl`, run from `starter/`. `--audit` is required: the server will not start without a file to record every call. Use the client's own configuration format; Lab 3.1's `relay-repo/.mcp.json` shows one common shape. Ask the agent to find overdue tasks in project 2, then ask it to "show me everyone's email address". Read `evidence/mcp-audit.jsonl` afterwards.

The `query` tool takes one argument, `request`, holding the whole request object. `tests/test_server.py` records why. In `mcp==2.3.0`, a typed argument is validated in lax mode (an `int` accepts `"5"` and `true`), and arguments the tool does not declare are dropped. Both happen before your function runs, so neither would be refused or audited by your policy. With one untyped `request`, every field inside it reaches the policy and the audit log. Only arguments sent *beside* `request` are still dropped unseen, and they carry nothing to the query.

**Known limits of this tool**, to carry into your threat model:

- The row cap is per call. Nothing stops an agent paging through a table with many calls; a per-session budget would.
- Redaction is by column. Personal data typed into free text, such as a task title, is returned as stored.
- Caller scoping is not implemented: every caller sees every project. Chapter 14 adds identity.
- The SQL dump is loaded before the connection is locked down, so the design assumes the agent cannot write to the dump file or the server's code.
- At the MCP layer, arguments sent beside `request` are dropped by the SDK before the tool runs, so they are neither refused nor audited. The audit hash covers the request object as delivered, re-serialized canonically.

### 8. Threat-model the workspace (30 min)

Copy `templates/workspace-threat-model.md` to `evidence/` and complete it for the Relay workspace of Lab 3.1, or for your own. Cite evidence for each control: an audit check ID from Lab 3.1, a test or a replayed attack from this lab.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/replay.md` | The generated replay report, plus your three extra attacks and their outcomes |
| `evidence/workspace-threat-model.md` | Every section, at least eight threats, evidence for each control, residual risks with owners |
| `evidence/mcp-audit.jsonl` | Optional: the audit log from a real MCP client session |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The replay sent 26 requests. All 8 legitimate requests were answered, returning 43 rows in total, with 12 values redacted (the names and emails of the 6 people on project 1). Of 18 attacks, 16 were refused before any SQL ran, under 11 different codes. The other two were answered harmlessly. A07's `' UNION SELECT email FROM users --` was bound as the LIKE pattern `%' UNION SELECT email FROM users --%` and matched no titles. A08's `%` matched only the 4 titles in project 1 that contain a literal percent sign. No response contained an email, name or hash from the database, the tables were unchanged, and the log holds 26 entries, one per call. Even with the policy bypassed, SQLite refuses DELETE, ATTACH, PRAGMA, `password_hash` and a four-way cross join.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `task_id: true` accepted | Use `type(value) is int`, not `isinstance`. |
| Wrong error code for a request with several problems | Follow the docstring's order exactly; size first, limit last. |
| `A08` returns 20 rows, truncated | `escape_like` is not applied, or the backslash is not escaped first. |
| `sqlite3.DatabaseError: not authorized` in your own query | The authorizer is working. Templates may read only allowlisted tables and non-secret columns. |
| `ModuleNotFoundError: mcp.server.mcpserver` | The `[mcp]` extra is not installed, or an mcp 1.x is installed (where the class was `FastMCP`). Install `mcp==2.3.0`. |
| The MCP client shows no tools | The server printed to stdout, or the path to `relay-test.sql` is relative to the wrong folder. Use absolute paths. |

## Cleanup

Nothing persists: the database lives in memory. Delete `evidence/mcp-audit.jsonl` if you do not need it, and remove the server from any MCP client configuration you added it to.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Policy correct | 3 | All tests pass against `starter/` |
| Adversarial thinking | 2 | Three new attacks, outcomes recorded, and A07/A08 explained from `--show` output |
| Audit design | 1 | Explains what the audit records, what it deliberately omits, and why it fails closed |
| Threat model | 3 | At least eight threats across all actors, each control backed by evidence, residual risks owned |
| MCP integration | 1 | Optional live session recorded, or a reasoned note on what the wrapper does and does not enforce |
