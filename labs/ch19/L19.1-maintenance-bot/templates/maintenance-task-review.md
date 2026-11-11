# Maintenance task type review

Fill this in for one task type in `relay-repo/maintenance/policy.json`. Every number must come from
`python -m mainlab.report month` or from a file you can name.

| Field | Your answer |
| --- | --- |
| Task type and tier | |
| What starts it, and is that source untrusted? | |
| Files it may write; protected paths it could reach if the policy were wrong | |
| Approvers (teams), and who is refused (the bot, its owner, non-owners) | |
| Guard metric, or why it has none | |
| Runs, task success with its interval | |
| Harm among merged changes with its interval | |
| Intervention frequency with its interval | |
| Policy violations, and what caused them | |
| Cost per run and per success | |
| Failing T4 criteria (A1 to A7), each with the evidence that would close it | |
| Merged changes needed for A1 at zero harms, and how long that takes at this rate | |
| Your recommendation: stay at its tier, narrow it, or start collecting evidence for a grant | |
| Reviewer (a person other than the bot's owner) and date | |
