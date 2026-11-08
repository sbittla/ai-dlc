# Test review record — written before the code

Spec: ESC-SPEC-1 1.1.0 · Tasks: T10, T14 · Author: <name> · Reviewer: <name, not the author, not an agent> · Date: <YYYY-MM-DD>

## 1. Criteria and sections covered

| Criterion or section | Tests named after it | Hand-worked example in a comment (yes/no) |
| --- | --- | --- |
| ESC-AC12 | | |
| B3: before opening, exactly at close, after close, weekends, daylight saving | | |
| ESC-AC15 | | |
| ESC-AC17 | | |
| ESC-AC27 | | |

## 2. Oracles

For each test file, say where expected values come from (spec text, hand calculation, standard-library recomputation, a law such as the EU daylight-saving rule) and paste the oracle check's result.

## 3. Red for the right reason

Paste the "fail on the starter stubs" rows of `evidence/grade-red.md`. Name any test you changed because it failed for another reason.

## 4. Seeded bugs

Which seeded bug was hardest to catch, and which sentence of the spec does the test that catches it check?

## 5. Reviewer's sign-off before the code

"I read each test against its criterion or spec section, and the expected values are independent of the implementation." Signed: <reviewer>, <date and time>. Commit of the approved tests: <hash>.

## 6. What these tests cannot see

At least three things, with the control that covers each (for example: transport across TB3 and TB4; daylight-saving changes inside a business window; a title that leaks through a field the test does not read).
