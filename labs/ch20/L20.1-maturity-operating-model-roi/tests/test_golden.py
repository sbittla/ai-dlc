"""Golden tests: every number Chapter 20 quotes from Lab 20.1, and the data's reproducibility."""

import json
import os
import subprocess
import sys

import pytest

from conftest import DATA_DIR, LAB_ROOT

from adoption.report import (render_adoption, render_catalog, render_maturity, render_plan, render_roi,
                             render_tom)


def test_maturity_january():
    text = render_maturity("2027-01", "relay")
    for line in ("| relay | 3 (4) | 2 (3) | 2 (3) | 1 (3) | 1 (3) | 1 (3) |",
                 "| mobile | 1 (3) | 1 (2) | 1 (2) | 1 (3) | 1 (3) | 1 (2) |",
                 "| integrations | 1 (2) | 1 (2) | 1 (2) | 1 (2) | 1 (3) | 1 (2) |",
                 "| analytics | 1 (3) | 1 (1) | 1 (3) | 1 (2) | 1 (4) | 1 (2) |",
                 "| marketplace | 1 (3) | 1 (2) | 1 (2) | 1 (3) | 1 (3) | 1 (3) |",
                 "Cells where the self-rating is higher than the evidence: 29 of 30",
                 "Evidence items: 29; not admissible on their own: 4",
                 "| data | 2 | D3.2 | older than 180 days |",
                 "| security | 1 | S2.2 | no evidence |"):
        assert line in text, line


def test_maturity_june():
    text = render_maturity("2027-06", "analytics")
    for line in ("| relay | 4 (4) | 3 (4) | 2 (4) | 2 (4) | 3 (3) | 2 (3) |",
                 "| mobile | 1 (2) | 1 (2) | 2 (2) | 2 (2) | 1 (2) | 2 (2) |",
                 "| integrations | 3 (3) | 3 (3) | 3 (3) | 3 (3) | 3 (3) | 2 (3) |",
                 "| analytics | 3 (3) | 3 (3) | 3 (3) | 3 (3) | 2 (3) | 2 (3) |",
                 "| marketplace | 1 (2) | 1 (2) | 1 (2) | 2 (2) | 1 (2) | 2 (2) |",
                 "Cells where the self-rating is higher than the evidence: 14 of 30",
                 "Evidence items: 83; not admissible on their own: 8",
                 "| culture | 2 | C3.1 | n 4 fails >= 5 |",
                 "| sponsorship | 2 | O3.1 | no evidence |"):
        assert line in text, line


def test_operating_model():
    assert "Capabilities: 10; funded effort: 0.50 FTE; findings: 0" in render_tom(False)
    draft = render_tom(True)
    assert "findings: 7" in draft
    assert "- TOM003 CAP08: the sponsor is accountable for, or approves, measuring the programme" in draft


def test_catalog():
    reviewed = render_catalog(False)
    assert "# Tool and MCP catalogue 2027.06.1 (approved 2027-06-15), checked as of 2027-06-15" in reviewed
    assert ("Previous version 2027.02.1 (approved 2027-02-26, with aup-v1): entries approved 4, prohibited 1; "
            "findings: 0") in reviewed
    assert "Entries: approved 4, prohibited 1, trial 1, under-review 1; findings: 0" in reviewed
    draft = render_catalog(True)
    assert "Entries: approved 5, prohibited 1, trial 1; findings: 10" in draft
    assert "Rules with findings: 8 (CAT001, CAT002, CAT003, CAT004, CAT005, CAT006, CAT007, CAT008)" in draft


def test_roi():
    text = render_roi(False)
    for line in ("Inputs: 18 (8 measured, 10 projected); findings: 0",
                 "Net hours per agent change: 1.49 (author 2.04 saved, review 0.55 added); over the pilot's 190 agent "
                 "changes: 283 hours, before any realization share",
                 "Agent changes: 1,604; gross hours released: 2,390; failure hours: 154; value per hour: $107.14",
                 "Benefit: $111,560",
                 "Cost: $218,005 (model $20,022, seats $12,840, platform and governance $90,000, training $43,714, "
                 "junior practice $51,429)",
                 "Net: -$106,445",
                 "Steady month after wave 3 (34 engineers, no training): benefit $11,816, cost $15,266, net -$3,450",
                 "Break-even author hours saved per agent change (others at base): 3.28",
                 "Break-even realization share (others at base): 0.92",
                 "Break-even author hours saved in the steady month: 2.42 (net of review: 1.87)",
                 "| author_hours_saved | measured | -$267,167 | $55,137 | $322,304 |",
                 "| change_fail_rate_delta | measured | $14,569 | -$227,459 | $242,029 |",
                 "| realization | projected | -$170,476 | -$42,414 | $128,062 |",
                 "| junior_practice_hours_per_month | projected | -$80,731 | -$157,874 | $77,143 |",
                 "| governance_fte | projected | -$79,445 | -$142,445 | $63,000 |"):
        assert line in text, line
    draft = render_roi(True)
    assert "Inputs: 19 (10 measured, 8 projected); findings: 10" in draft
    assert "Rules with findings: 7 (ROI001, ROI002, ROI003, ROI004, ROI005, ROI006, ROI007)" in draft
    assert "Refused: the model does not run on inputs with findings." in draft


def test_adoption_and_plan():
    a = render_adoption()
    assert "2027-01-20: 13 of 31 respondents (31 of 34 engineers answered)" in a
    assert "2027-05-28: 2 of 30 respondents (30 of 34 engineers answered)" in a
    assert "Amnesty 2027-02-26 to 2027-03-12: 7 reports; credentials rotated: 1" in a
    assert "not the refund pilot's key" in a and "reported in the amnesty: no" in a
    assert "Paste filter, 2027-03-01 to 2027-05-28: 4 pastes containing a secret blocked" in a
    p = render_plan()
    assert "Engineer-months with agents to 2028-06-30: 321" in p
    assert "| 2 | mobile | 9 | 2027-10-01 | 9 | 81 |" in p


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_generated_json_file_is_labelled():
    for path in sorted(DATA_DIR.rglob("*.json")):
        if "relay-4.30.0" in path.parts:
            continue
        assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"], path.name


def test_measured_inputs_match_lab_20_2():
    """The pilot's measured inputs are copied from Lab 20.2's printed values; check them when that lab is here."""
    lab = LAB_ROOT.parent / "L20.2-controlled-adoption-experiment"
    if not (lab / "solution").is_dir():
        pytest.skip("Lab 20.2 is not in this checkout")
    code = ("import json,sys; sys.path.insert(0, 'solution'); from experiment.report import roi_inputs; "
            "print(json.dumps(roi_inputs()))")
    out = subprocess.run([sys.executable, "-c", code], cwd=lab, check=True, capture_output=True, text=True,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}).stdout
    pilot = json.loads(out)
    ours = {i["id"]: i for i in json.loads((DATA_DIR / "roi" / "inputs-reviewed.json").read_text(
        encoding="utf-8"))["inputs"]}
    assert [ours["author_hours_saved"][k] for k in ("value", "low", "high")] == \
        pilot["author_hours_saved_per_agent_change"]
    assert [ours["review_hours_added"][k] for k in ("value", "low", "high")] == \
        pilot["review_hours_added_per_agent_change"]
    assert [ours["change_fail_rate_delta"][k] for k in ("value", "low", "high")] == \
        pilot["change_fail_rate_delta_points"]
    assert ours["model_usd_per_agent_change"]["value"] == pilot["model_usd_per_agent_change"]
    assert ours["changes_per_engineer_month"]["value"] == pilot["changes_per_engineer_month"]


def test_relay_copies_match_canonical_4_30_0():
    relay = LAB_ROOT.parent.parent / "relay-baselines" / "4.30.0" / "relay-repo"
    if not relay.is_dir():
        pytest.skip("canonical Relay 4.30.0 is not in this checkout")
    for name, src in (("mcp.json", relay / ".mcp.json"),
                      ("ai-components.json", relay / "supply-chain" / "ai-components.json"),
                      ("agents.json", relay / "governance" / "agents.json")):
        ours = (DATA_DIR / "catalog" / "relay-4.30.0" / name).read_bytes()
        assert ours == src.read_bytes().replace(b"\r\n", b"\n"), name
