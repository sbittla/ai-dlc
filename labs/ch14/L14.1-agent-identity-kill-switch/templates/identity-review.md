# Agent identity review

Copy to `evidence/identity-review.md`.

## 1. Inventory

How was the inventory built? List the systems you read it from (Relay's token list, IAM roles and CloudTrail,
GitHub's apps, tokens and secrets, MCP server configurations) and anything you could not list.

## 2. Findings before and after

Paste the summary lines of `report identities` for both inventories. For each credential with no expiry in the
first, say what replaced it.

## 3. Detection

Paste the alert summary of `report detect --seeded`. For each seeded case that was missed, name the control that
covers it instead. Which alert would you page on, and which would you only record? Why?

## 4. Kill switch

Paste the drill table. Explain DRILL-1's result in two sentences. Which numbers in the table are measured, and
which are assumed?

## 5. Caller scoping

Paste the scoping table. What would the steered session have read from another customer's workspace without
scoping?

## 6. Residual risks

At least three, each with an owner and a review date. Start with the ones the chapter's "Known limits" names.

## 7. What an agent produced

Which parts of this review, and of your code, did an agent write, and how did you check each?
