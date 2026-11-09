# Integration plan — parallel agents

## 1. Tasks and partition
| Task | Pull request | Files it touches | Depends on | Worktree and branch |
| --- | --- | --- | --- | --- |

## 2. Waves and predicted overlaps
<Waves, from the dependencies. Every file two tasks in one wave both touch, and what you did about it: re-partition, sequence, or accept and merge.>

## 3. Integration order and the check after each step
<The order, and what runs after each merge: the characterization, the module's tests, the full suite.>

## 4. Conflicts and how each was resolved
| Step | File and lines | Textual or semantic | Resolution (merge by hand, re-run the agent, re-partition) | Checked by |
| --- | --- | --- | --- | --- |

## 5. Rollback at each step
<What undoing each pull request takes: a revert, a configuration change, or a restore. Which steps cannot be undone by a revert alone?>
