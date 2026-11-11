"""Golden tests: every number Chapter 20 quotes from Lab 20.2, and the data's reproducibility."""

import hashlib
import json
import subprocess
import sys

import pytest

from conftest import DATA_DIR, LAB_ROOT

from experiment.report import (render_baseline, render_config, render_power, render_prereg, render_readout,
                               roi_inputs)


@pytest.fixture(scope="module")
def power_text():
    return render_power()


@pytest.fixture(scope="module")
def readout():
    return render_readout()


def test_baseline():
    text = render_baseline()
    assert "# Baseline quarter (13 weeks, 5 October 2026 to 1 January 2027, four teams)" in text
    assert "Changes: 850; engineers: 34; changes per engineer-week: 1.92" in text
    assert "Mean author hours per change: 10.79; mean review hours per change: 2.13" in text
    assert "Median change lead time: 46.5 h" in text
    assert "sd_team 0.067, sd_engineer 0.065, sd_residual 0.428" in text


def test_configured_effects():
    text = render_config()
    for line in ("- Change fail rate: 7.6% control, 9.6% agent (a harm of +2.0 points)",
                 "- Perceived saving asked of the pilot teams: centred on 0.31",
                 "- Expected lead-time ratio under this configuration (100,000 simulated changes): 0.996",
                 "two-sided 5%, normal approximation: 0.10",
                 "- Changes per arm needed for 80% power against that harm: 3,081"):
        assert line in text, line


def test_power_table(power_text):
    for line in (
        "| D1 team level, 2 pilot vs 2 comparison teams, before and after | team | 34 | 0.164 | 0.100 | 0.056 |",
        "| D2 engineer level, half of each team on agents | engineer | 34 | 0.937 | 0.733 | 0.363 |",
        "| D3 task level within the two pilot teams | task (analyzed within engineer) | 15 | 0.879 | 0.622 | 0.321 |",
        "| D4 task level within all four teams | task (analyzed within engineer) | 34 | 0.998 | 0.944 | 0.667 |",
        "- D1 with sd_team_period 0.00: power 0.655",
        "- D1 with sd_team_period 0.05: power 0.324",
        "- D2 with contamination_engineer 0.50: power 0.718",
        "- D3 with contamination_task 0.40: power 0.642",
        "- D3 needs 23 weeks for 80% power at a true ratio of 0.85",
        "- D3 sign test: power 0.690, 0.441, 0.175 at 0.80, 0.85, 0.90",
        "- D4 sign test: power 0.954, 0.738, 0.373 at 0.80, 0.85, 0.90",
        "- D3 with the sign test needs 20 weeks for 80% power at a true ratio of 0.80",
    ):
        assert line in power_text, line


def test_prereg():
    reviewed = render_prereg(False)
    assert "Design D3; registered test: paired t-test; stated power 0.879 at ratio 0.80; recomputed 0.879" in reviewed
    assert "Findings: 0" in reviewed
    draft = render_prereg(True)
    assert "stated power 0.900 at ratio 0.80; recomputed 0.164" in draft
    assert "Findings: 14" in draft
    assert ("Rules with findings: 11 (REG001, REG002, REG003, REG004, REG005, REG006, REG007, REG008, REG009, "
            "REG010, REG011)") in draft


def test_readout(readout):
    for line in (
        "Pilot changes in the two pilot teams: 382 (190 agent, 192 control); engineers with both arms: 15",
        "| Change lead time (primary) | 1.03 | 0.91 to 1.17 | 0.619 | 6 lower, 9 higher | 0.607 |",
        "| Author hours | 0.69 | 0.56 to 0.86 | 0.002 | 14 lower, 1 higher | 0.001 |",
        "| Review hours | 1.29 | 1.14 to 1.46 | 0.001 | 3 lower, 12 higher | 0.035 |",
        "| Review wait | 1.42 | 1.23 to 1.63 | 0.000 | 1 lower, 14 higher | 0.001 |",
        "| Author hours saved | 2.04 | 0.17 to 3.92 | 0.035 | 12 saved, 3 lost | 0.035 |",
        "| Review hours saved | -0.55 | -0.87 to -0.22 | 0.003 | 3 saved, 12 lost | 0.035 |",
        "| Net hours saved | 1.50 | -0.56 to 3.56 | 0.141 | 10 saved, 5 lost | 0.302 |",
        "Check: the percentile cluster bootstrap for author hours saved gives 0.42 to 3.69, against the t interval's "
        "0.17 to 3.92; 13% narrower with 15 clusters",
        "Change fail rate: agent 16 of 190, control 16 of 192; within-engineer difference +0.6 points (-3.8 to +5.0), "
        "t-test p = 0.772",
        "| integrations | pilot | 10.1 | 14.4 |",
        "| analytics | pilot | 9.0 | 10.2 |",
        "| mobile | comparison | 8.7 | 8.8 |",
        "| marketplace | comparison | 7.8 | 9.8 |",
        "Guardrail: pilot-to-comparison median review wait 1.31 in the pilot (12.1 h against 9.3 h) and 1.20 in the "
        "baseline (9.6 h against 8.0 h); pilot over baseline 1.09 (threshold 1.5)",
        "Perceived time saved on agent tasks (week 13; integrations, n = 8): 34%; not reported for analytics (n < 5)",
        "Unassisted debugging, pilot teams: passed 11 of 15 before, 10 after; discordant 1 and 0, exact McNemar "
        "p = 1.000",
        "Unassisted debugging, comparison teams: passed 15 of 19 before, 17 after; discordant 0 and 2, exact McNemar "
        "p = 0.500",
        "| mobile | post | 4 | suppressed (n < 5) | | | |",
    ):
        assert line in readout, line


def test_roi_inputs_lab_20_1_uses():
    v = roi_inputs()
    assert v["net_hours_saved_per_agent_change"] == (1.5, -0.56, 3.56)
    assert v["author_hours_saved_per_agent_change"] == (2.04, 0.17, 3.92)
    assert v["review_hours_added_per_agent_change"] == (0.55, 0.22, 0.87)
    assert v["change_fail_rate_delta_points"] == (0.6, -3.8, 5.0)
    assert v["model_usd_per_agent_change"] == 12.48
    assert v["changes_per_engineer_month"] == 8.33


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_json_file_is_labelled_and_the_registration_binds_the_assignment_list():
    for path in sorted(DATA_DIR.rglob("*.json")):
        assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"], path.name
    reg = json.loads((DATA_DIR / "prereg" / "prereg-reviewed.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((DATA_DIR / "assignments.csv").read_bytes()).hexdigest()
    assert reg["randomization"]["assignment_list_sha256"] == digest
    assert reg["registered_on"] < reg["start"]
    frozen = json.loads((DATA_DIR / "prereg" / "frozen.json").read_text(encoding="utf-8"))
    assert frozen["sha256"] == hashlib.sha256((DATA_DIR / "prereg" / "prereg-reviewed.json").read_bytes()).hexdigest()
