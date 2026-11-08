# Lab 1.2 — Audit a Vendor Productivity Claim

| | |
| --- | --- |
| Chapter | 1 — From SDLC to Evidence-Driven Engineering |
| Type | Stretch (all tracks); recommended for Leaders |
| Time | 2 hours |
| Cost ceiling | $0 (runs locally) |
| Requires | Python 3.11+ and pytest (`pip install -e ".[dev]"`). No other packages. |

## Brief

A vendor, **Tachyon Agents** (fictional), is pitching Relay's leadership. Their slide reads:

> **Developers using Tachyon Agents finished tasks 38% faster.**
> Controlled trial · 300 task attempts · 24 developers

Your CTO asks: *"Is this real, and would it be real for us?"* The vendor has shared the raw trial data (`data/trial.csv`). You will reproduce the headline, then test it the way an auditor would, and write a one-page memo with a recommendation.

Relay's product owner has estimated next quarter's backlog by effort:

| Task size | Meaning | Share of Relay's backlog |
| --- | --- | --- |
| S | about an hour | 25% |
| M | about half a day | 45% |
| L | a day or more | 30% |

## What you will practise

- Reproducing a headline number before trusting or rejecting it.
- Checking whether the comparison groups were comparable (selection bias, Simpson's paradox).
- Standardizing a result to **your** situation instead of the vendor's.
- Putting an uncertainty interval on an estimate, and adjusting speed for quality.

## Data

`data/trial.csv` has one row per task attempt:

| Column | Meaning |
| --- | --- |
| `attempt_id` | unique ID of the attempt |
| `developer_id` | who did it (24 developers; each worked in both arms) |
| `arm` | `control` (no agent) or `ai` (with Tachyon Agents) |
| `task_size` | `S`, `M` or `L` |
| `minutes` | time from task start to pull request opened (review, merge and deployment are not included) |
| `passed_review` | whether the change passed code review first time |
| `defects_30d` | defects traced to the change within 30 days |

## How "X% faster" is measured

Throughout this lab, "38% faster" means **38% less time**: speedup = 1 − (AI minutes ÷ control minutes). That is the vendor's convention, and the one Peng et al. (2023) use. 38% less time is about 1.6 times the speed (1 ÷ 0.62 ≈ 1.61). A negative speedup means the AI arm took longer.

## Steps

1. **Reproduce the headline (15 min).** Implement `naive_speedup` in `starter/audit/analysis.py`. Confirm you get the vendor's 38%.
2. **Check comparability (20 min).** Implement `task_mix`. Did both arms work on the same kinds of tasks?
3. **Split the effect (20 min).** Implement `speedup_by_size`. Does the agent help equally on all task sizes?
4. **Standardize to Relay (20 min).** Implement `reweighted_speedup` and `bootstrap_ci`. What speedup should Relay expect for *its* mix, and how sure can it be?
5. **Adjust for quality (15 min).** Implement `acceptance_rate` and `minutes_per_accepted_task`.
6. **Run the report and write the memo (30 min).**

Tests grade `starter/` by default. To check the reference: `LAB_TARGET=solution python -m pytest -q` (bash), or in PowerShell `$env:LAB_TARGET="solution"; python -m pytest -q; Remove-Item Env:LAB_TARGET`.

```bash
python -m pytest -q                       # from the lab folder
cd starter
python -m audit.report --data ../data/trial.csv > ../evidence/audit-findings.md
python -m audit.report --data ../data/trial.csv --mix S=0.6,M=0.3,L=0.1   # sensitivity check
```

Copy `templates/audit-memo.md` to `evidence/audit-memo.md` and complete it.

## Expected evidence

| File | Must contain |
| --- | --- |
| `evidence/audit-findings.md` | The generated findings table |
| `evidence/audit-memo.md` | One page: headline reproduced, three problems found, Relay-specific estimate with interval, recommendation |
| Passing tests | `python -m pytest -q` passes against `starter/` |

## Sample of acceptable evidence (excerpt)

> The vendor's 38% reproduces from the raw data, but it compares different work. 61% of AI-arm attempts were small tasks versus 36% in the control arm. Split by size, the agent was about 30% faster on small tasks, about 2% faster on medium tasks and about 17% *slower* on large tasks. Standardized to Relay's backlog (25% S, 45% M, 30% L), the expected effect is −7% (slower), with a 95% interval from −22.0% to +6.5%: the trial gives no evidence of a speedup for our work. Per *accepted* task, the AI arm was about 10% slower. Defects reverse the same way: raw, the AI arm had fewer defects per attempt (0.44 vs 0.49), but standardized to our mix it had more (0.67 vs 0.53), because it avoided the large tasks where defects concentrate. With a mix like the vendor's AI arm (60% S, 30% M, 10% L), the expected speedup is +3.8%: the agent may help on a backlog of small tasks, which is what a pilot should test. **Recommendation:** do not buy on this evidence; propose a four-week pilot on our own small-task backlog, with the guardrails from Lab 1.1.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Naive speedup is not 38.2% | Use means, not medians, and pool all task sizes. |
| `reweighted_speedup` disagrees with the tests | Weight each arm's *per-size mean* by the same mix; do not reweight individual rows. |
| Bootstrap interval differs | Follow the numbered algorithm in the `bootstrap_ci` docstring exactly: cell order, `rng.choice` per row, index rule. |

## Known limitations of this data

- **Small cells.** The AI arm has only 13 large-task attempts. Their review pass rate (92%) is higher than the AI arm's other sizes, which is probably noise. Say so rather than build conclusions on it.
- **Clustering.** Each developer contributes about 12 attempts. The bootstrap treats attempts as independent, so the interval is somewhat too narrow. A cluster bootstrap that resamples developers would widen it; mention this in your memo.

## Cleanup

Nothing to clean up.

## Rubric (10 points)

| Criterion | Points | Full marks when |
| --- | --- | --- |
| Analysis correct | 3 | All tests pass against `starter/` |
| Problems identified | 3 | Selection bias, size-dependent effect and quality cost each explained with numbers |
| Relay-specific estimate | 2 | Standardized estimate with interval, and a sensitivity check with a different mix |
| Recommendation | 2 | Clear decision, the evidence that would change it, and a pilot design with guardrails |
