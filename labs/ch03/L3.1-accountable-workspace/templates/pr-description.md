# <ticket>: <one-line summary of the change>

## Claim

One sentence a reviewer can check. Example: "Due dates display as stored for viewers in every supported time zone."

## Why

The defect, who it affects, and how you reproduced it (command and output).

## What changed

| File | Change |
| --- | --- |
| | |

## Evidence

| Check | Command | Commit | Result |
| --- | --- | --- | --- |
| Failing test first | | | |
| Full suite after the fix | | | |
| Lint | | | |
| Workspace audit | | | |

## Risk and rollback

What could this break, who would notice first, and how to revert.

## AI-use disclosure

- Agent and version, or "none":
- What the agent produced (test, fix, description):
- What you checked yourself, line by line:
- Instructions file and commit the agent read:

## Reviewer checklist

- [ ] The new test fails on the old code and passes on the new code (see the commits).
- [ ] Every name in the diff exists (functions, settings, commands).
- [ ] No secrets, credentials or `.env` files in the diff.
- [ ] The change is the smallest one that makes the claim true.
- [ ] The author of record can explain every line.
