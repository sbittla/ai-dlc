"""Lab 9.1's pull-request kit: measure a change, check it before review, and verify an agent's claims.

    diffs.py       changed lines between two versions of a file (provided)
    codeowners.py  who must review a path, from .github/CODEOWNERS (provided)
    series.py      Relay 4.22.0's pull requests, measured from 4.21.0 (provided)
    prcheck.py     the pull-request check, PR01 to PR09 (check_pr is a TODO in starter/)
    claims.py      checks an agent's claims about the code against the source (verify_claim is a TODO)
    live.py        optional: ask a Claude model to review a diff (gated; never needed)
    report.py      python -m prkit.report incident | claims | series | release
"""
