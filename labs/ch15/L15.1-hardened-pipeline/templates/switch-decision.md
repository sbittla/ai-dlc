# Switch from verify-only to deliver

Copy into `evidence/` and complete. ADR-044 sets the conditions; this record is what platform leads read before
they set `RELAY_PIPELINE_MODE` to `deliver`.

| | |
| --- | --- |
| Date of the decision | |
| Decided by (two people) | |
| First release through the pipeline | |

## Condition 1: Gate G4's adversarial row

Paste `python -m pipeline.report g4 --as-of <date>`. The row cannot be waived.

## Condition 2: agreement with the train

From `python -m pipeline.report train`: for each release the pipeline would have stopped, say why, and whether the
reason is now gone. Any disagreement you cannot explain stops the switch.

## Condition 3: the way back

- How is a bad release rolled back, and how long does it take?
- Who can set the mode back to `verify-only`, and when would they?

## What changes for people

The train's fixed time goes. Who is on hand during a rollout, and what replaces "just this once"?
