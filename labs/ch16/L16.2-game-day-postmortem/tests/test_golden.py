"""Every number Chapter 16 quotes from Lab 16.2, locked: each report's full output must match tests/golden/.

If a change to the data or the code moves a number, this fails, and the chapter must be updated with it.
Regenerate a golden file only with the chapter text:
`python -m gameday.report <name> > ../tests/golden/<name>.txt` (UTF-8; not UTF-16 from Windows PowerShell 5.1).
"""

from pathlib import Path

import pytest

from gameday.report import COMMANDS

GOLDEN = Path(__file__).resolve().parent / "golden"


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_report_matches_golden(name, capsys):
    COMMANDS[name]()
    assert capsys.readouterr().out == (GOLDEN / f"{name}.txt").read_text(encoding="utf-8")
