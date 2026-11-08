# Chapter 3 — Answers and Marking Notes

## Recall

**1. Six agent modes.** From Table 3.1:

| Mode | Can touch | A person checks |
| --- | --- | --- |
| Autocomplete | Text at the cursor | Immediately, on accepting each suggestion |
| Chat | Nothing directly; you copy its output | When you paste and run it |
| Edit | Selected files in the editor | When reviewing the diff |
| IDE agent | The open project and editor-launched commands | Per action or at the end, depending on its permission mode |
| Terminal agent | Whatever the shell's user can reach | Per action or at the end, depending on its permission mode |
| Background agent | A remote environment it is given | When reviewing its pull request |

Full marks need the "can touch" column to grow down the list and the approval point to move later.

**2. Instruction file sections and why it is not a control.** Project overview, Commands, Architecture, Conventions, Boundaries. It is not a control because a model follows instructions with high probability, not certainty, and other text in its context (including injected instructions) competes with them. Any rule that matters must be enforced where the model cannot change it: branch protection, sandbox configuration, tool lists, the absence of secrets. Deduct marks for answers that say a better-worded instruction would be enough.

**3. Trust boundaries in Figure 3.3.** Any threat that fits each boundary earns the mark:
- Untrusted content becomes model context: prompt injection in a ticket or web page steers the agent.
- Model-chosen arguments reach the server: injection or out-of-range values in tool arguments (SQL in a parameter, a huge limit).
- The server's credentials and network: a server running as you can read your files, reach your network, or use an overly broad connection string. Its descriptions and results flow back as context, so tool poisoning also fits here.

**4. Lethal trifecta.** Access to private data, exposure to untrusted content, and the ability to communicate externally. In a developer workspace, untrusted content is hardest to remove (tickets, issues, dependencies, web pages). The easiest parts to remove are private data in reach (no secrets in the sandbox or context) and external communication (limit network egress). Either breaks the exfiltration path.

## Apply

**5. Hand audit.** Eight open findings (checked by running Lab 3.1's reference audit on a repository built to the description):

| Severity | Findings |
| --- | --- |
| critical (3) | WS021 `~/.kube` mount; WS010 on each of the two secret lines in `.env` |
| high (4) | WS011 `.env` committed; WS022 `--network=host`; WS033 twice (`tests` and `secret-scan` not required) |
| medium (1) | WS036 no `CODEOWNERS` |
| low (0) | Image pinned by digest, so no WS023 |

There is no WS034 or WS037: protection applies to administrators, and both stale-approval settings are on.

Fix first: treat both secrets as exposed and rotate them, then remove `.env` from the repository (and its history) and add it to `.gitignore`. Remove the `~/.kube` mount, which gives any process in the container the developer's cluster credentials. Next require the status checks, because without a required `secret-scan` the next secret can merge unnoticed. A strong answer notices that code-owner review is required but has no effect without a `CODEOWNERS` file.

**6. The old rounding.** For a due date of 20 November 2026, local midnight is converted to UTC, 12 hours are added, and the date is taken:

| Offset | Local midnight in UTC | Plus 12 hours | Shown |
| --- | --- | --- | --- |
| +12:00 | 19 Nov 12:00 | 20 Nov 00:00 | 20 Nov (correct) |
| +12:45 | 19 Nov 11:15 | 19 Nov 23:15 | 19 Nov (one day early) |
| −11:00 | 20 Nov 11:00 | 20 Nov 23:00 | 20 Nov (correct) |
| −12:00 | 20 Nov 12:00 | 21 Nov 00:00 | 21 Nov (one day late) |

The last row shows the old code was also wrong at UTC−12, an offset none of Relay's 14 supported zones uses. The regression test covers the zones Relay supports, so it could not reveal this. Good answers draw two lessons. Test data should include boundary values (±12:00, fractional offsets), not only the reported case. And the fix is right for every offset because it removes the conversion entirely, which is a stronger argument than any finite test table.

**7. LIKE escaping.** The bound pattern is `%50\%\_off%` (backslash escapes, `ESCAPE '\'`). Unescaped, `%50%_off%` would treat `%` as "any run of characters" and `_` as "any one character", so it would match any title with "50", then anything, then one character, then "off". Binding stops the value from changing the SQL statement. It does not stop LIKE from interpreting its own wildcards inside the bound value, so without escaping a caller can broaden a search (`%` matches every task, as request A08 tried) or write slow patterns. Full marks need the exact pattern and the distinction between SQL syntax and the LIKE pattern language.

## Design

**8. Overnight background agent.** Look for:
- **Sandbox:** an ephemeral environment per task, workspace-only files, no host mounts, egress limited to the package index and the code host, no long-lived credentials, no privileged mode; destructive commands impossible rather than merely approved, since nobody is watching.
- **Identity:** a dedicated bot account that can push branches and open pull requests, and cannot approve, merge, change branch protection or edit `governance/` and `.github/`.
- **Context:** the repository's instruction file; perhaps a skill for the team's test conventions; a read-only reviewer subagent. Issue text treated as untrusted (cap at T2, Chapter 1).
- **Branch protection:** pull request required, at least one approving human review, code-owner review, approval of the most recent push, required `tests` and `secret-scan` checks, applied to administrators, force pushes blocked.
- **Evidence per pull request:** the issue link and claim, the failing-test commit before the fix, CI results, the workspace audit result, an AI-use disclosure and session log, and the human reviewer.
- Full marks need the bot identity's inability to approve and the absence of credentials worth stealing.

**9. Workspace-configuration lookup tool.** Look for:
- **Templates:** a small set, such as `workspace_plan(workspace_id)`, `sso_status(workspace_id)` and `webhook_health(workspace_id)`, each returning named, non-secret columns.
- **Parameters:** a typed workspace id with bounds; ideally the caller's ticket must reference the same workspace, checked in code. Row caps, and a request size limit.
- **Redaction:** no emails, names, tokens, SAML certificates or webhook secrets; return booleans or expiry dates instead of secrets ("SAML certificate expires 2027-03-01", not the certificate).
- **Audit:** caller, ticket id, template, validated parameters, outcome, row count, request hash; never the raw request or the returned data; fail closed.
- **Adversarial tests first:** a workspace id belonging to a different ticket's customer; SQL or extra fields in parameters; a request for a secret column through an extra parameter; an oversized limit.
- **Trifecta:** the design removes private data from reach (secrets never returned) and, if the tool is the agent's only external access, limits exfiltration paths. Untrusted content (the ticket) remains, which is why the tool's output must be harmless even if the agent is steered.
