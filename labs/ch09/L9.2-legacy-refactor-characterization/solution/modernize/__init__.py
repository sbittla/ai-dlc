"""Lab 9.2: modernize legacy code behind characterization tests, with parallel agents in worktrees.

    paths.py      where the data, the oracle and the candidates live (provided)
    charact.py    characterization: compare a candidate with the legacy module (compare_decisions,
                  classify_prefs are TODOs in starter/)
    migration.py  replay a migration on production-shaped data and count what it lost (losses is a TODO)
    merge.py      a line-based three-way merge that reports overlapping changes as conflicts (provided)
    parallel.py   waves, integration order and integration of worktrees (integration_order is a TODO)
    probe.py      runs one characterization in a fresh interpreter (provided)
    report.py     python -m modernize.report incident | characterize | parallel
"""
