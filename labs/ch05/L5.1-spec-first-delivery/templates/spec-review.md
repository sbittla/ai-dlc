# Spec review record — <spec ID> version <x.y.z>

Copy to `evidence/spec-review.md` and complete every section.

## 1. What the checker reported

- Scaffold (before your work): <total> findings, <blocking> blocking. Paste the summary table.
- Your package (after): <total> findings, <blocking> blocking. Warnings answered below.
- The assistant's draft task list (`data/tasks-draft.md`): the three findings that would have done most harm if an agent had worked from it, and why.

## 2. Scope decisions

- Criteria in the slice, and why each is in: <list>.
- Criteria you marked `partial`, and what each defers to which later stage: <list>.
- One criterion you left out that a reader might expect in, and why.

## 3. Data classification

- Fields classified Confidential or Restricted, and the rule that keeps each out of documents for delivery.
- Which outbound field you were least sure about, and how you decided.

## 4. Security constraints

For each constraint: its source in the PRD, the executable check that tests it, and one way it could still be broken that the check would not see.

## 5. Tasks and tiers

- Waves and longest chain from `--plan`.
- Each task that reads untrusted input or is sensitive, its tier, and the Chapter 1 rule that sets it.

## 6. What the checks cannot tell you

Name three things a clean report does not prove (for example: a criterion tested at the component boundary only; a test that passes but asserts less than its criterion; a data rule that is correct for this slice but wrong for delivery). For each, name the human step that covers it.

## 7. Approval

- Product owner, tech lead and security reviewer, and how each approval was given (a required code-owner review on the pull request that sets `Status: approved`, or the lab's stand-in). None of them can be you if you wrote the spec, and none can be an agent.

## 8. AI-use disclosure

What an assistant or agent produced (spec text, tasks, code, tests), and how you checked each.
