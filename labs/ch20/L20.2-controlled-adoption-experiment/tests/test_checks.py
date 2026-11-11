"""Hand-checkable tests for the three TODOs and the provided statistics helpers."""

import copy
import json
import math

import pytest

from conftest import DATA_DIR

from experiment.analysis import paired_t, within_engineer_log_ratio
from experiment.power import simulate_power
from experiment.prereg import check_frozen, check_prereg
from experiment.stats import binom_two_sided, t_cdf, t_quantile

COMPS = {"sd_team": 0.07, "sd_engineer": 0.07, "sd_residual": 0.43}
SIZES = {"mobile": 9, "integrations": 8, "analytics": 7, "marketplace": 10}


# --- provided helpers -------------------------------------------------------------------------------------------

def test_exact_binomial_two_sided():
    assert binom_two_sided(0, 5) == pytest.approx(2 / 32)
    assert binom_two_sided(1, 14) == pytest.approx(2 * 16 / 2 ** 15)
    assert binom_two_sided(3, 3) == 1.0 and binom_two_sided(0, 0) == 1.0


def test_t_quantiles_match_published_tables():
    assert t_quantile(0.975, 14) == pytest.approx(2.1448, abs=0.002)
    assert t_quantile(0.975, 2) == pytest.approx(4.3027, abs=0.003)
    assert t_quantile(0.975, 33) == pytest.approx(2.0345, abs=0.002)


# --- TODO 3: the paired t-test, and the within-engineer ratio built on it ------------------------------------------

def test_paired_t_by_hand():
    # mean 2, sample sd 1 (divisor 3), se 0.5, t = 4 on 3 df
    m, lo, hi, p = paired_t([1.0, 2.0, 3.0, 2.0])
    assert m == pytest.approx(2.0)
    half = t_quantile(0.975, 3) * (2 / 3) ** 0.5 / 2
    assert (lo, hi) == (pytest.approx(2.0 - half), pytest.approx(2.0 + half))
    assert p == pytest.approx(2 * (1 - t_cdf(2.0 / ((2 / 3) ** 0.5 / 2), 3)))
    assert paired_t([1.0, 1.0]) == (1.0, 1.0, 1.0, 0.0) and paired_t([0.0, 0.0]) == (0.0, 0.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        paired_t([1.0])


def _row(eng, arm, hours):
    return {"engineer": eng, "arm": arm, "lead_time_hours": hours}


def test_within_engineer_ratio_by_hand():
    rows = [_row("e1", "agent", 2.0), _row("e1", "agent", 8.0), _row("e1", "control", 4.0),
            _row("e2", "agent", 1.0), _row("e2", "control", 2.0), _row("e2", "control", 2.0),
            _row("e3", "agent", 5.0)]  # e3 has no control task and is left out
    r = within_engineer_log_ratio(rows, "lead_time_hours")
    # e1: mean log agent = log 4 = mean log control, d = 0. e2: d = log 1 - log 2 = -log 2. Mean d = -log 2 / 2.
    assert r["estimate"] == pytest.approx(2 ** -0.5)
    assert r["engineers"] == 2 and r["positive"] == 0 and r["negative"] == 1
    assert r["sign_test_p"] == 1.0
    # differences 0 and -log 2: t = 1 on 1 df, so the two-sided p is 0.5
    assert r["t_test_p"] == pytest.approx(0.5, abs=1e-3)
    assert r["low"] < r["estimate"] < r["high"]


def test_within_engineer_ratio_is_deterministic_and_seeded():
    rows = [_row(f"e{i}", arm, h) for i in range(6) for arm, h in (("agent", 3.0 + i), ("control", 4.0 + i))]
    a = within_engineer_log_ratio(rows, "lead_time_hours", seed=1)
    assert a == within_engineer_log_ratio(rows, "lead_time_hours", seed=1)
    assert a["negative"] == 6 and a["sign_test_p"] == pytest.approx(2 / 64)


# --- TODO 2: the pre-registration check ----------------------------------------------------------------------------

@pytest.fixture()
def reviewed():
    return json.loads((DATA_DIR / "prereg" / "prereg-reviewed.json").read_text(encoding="utf-8"))


def rules(reg, power=None, sha=None):
    return {f.rule for f in check_prereg(reg, power, sha)}


def test_reviewed_registration_passes(reviewed):
    assert rules(reviewed, reviewed["power"]["power"], reviewed["randomization"]["assignment_list_sha256"]) == set()


@pytest.mark.parametrize("change, rule", [
    (lambda r: r.update(registered_on=r["start"]), "REG001"),
    (lambda r: r["primary_outcome"].update(metric="author_hours"), "REG002"),
    (lambda r: r["secondary_outcomes"].append({"metric": "prompts_per_engineer"}), "REG003"),
    (lambda r: r["randomization"].update(method="teams that volunteered"), "REG004"),
    (lambda r: r["randomization"].update(seed=None), "REG004"),
    (lambda r: r["randomization"].update(who_assigns=r["sponsor"]), "REG004"),
    (lambda r: r.update(comparison_group=" "), "REG005"),
    (lambda r: r.update(contamination=[{"risk": "x", "mitigation": ""}]), "REG006"),
    (lambda r: r["power"].update(power=0.79), "REG007"),
    (lambda r: r["power"].update(design="D4"), "REG007"),
    (lambda r: r["analysis"].update(cluster_unit="task"), "REG008"),
    (lambda r: r["analysis"].update(interim_looks="weekly; stop when clear"), "REG008"),
    (lambda r: r["analysis"].update(interim_looks="none, apart from a weekly peek at the dashboard"), "REG008"),
    (lambda r: r["analysis"].update(interim_looks="weekly dashboard peeks; no alpha spending"), "REG008"),
    (lambda r: r["analysis"].update(test="none"), "REG008"),
    (lambda r: r.update(registered_on="2027-3-01"), "REG001"),
    (lambda r: r["secondary_outcomes"].append({"metric": "commit_count"}), "REG003"),
    (lambda r: r["secondary_outcomes"].append({"metric": "story_points"}), "REG003"),
    (lambda r: r["secondary_outcomes"].append({"metric": "velocity"}), "REG003"),
    (lambda r: r["randomization"].update(seed=""), "REG004"),
    (lambda r: r["randomization"].update(method="team leads pick the tasks before the start"), "REG004"),
    (lambda r: r["randomization"].update(method="engineers opt in task by task"), "REG004"),
    (lambda r: r["randomization"].update(method="assigned by the data steward"), "REG004"),
    (lambda r: r["randomization"].update(who_assigns=" Engineering-Director "), "REG004"),
    (lambda r: r.update(analysis_owner="Engineering-Director"), "REG010"),
    (lambda r: r["guardrails"][0].update(threshold="TBD", window="TBD"), "REG009"),
    (lambda r: r.update(guardrails=[g for g in r["guardrails"] if g["metric"] != "change_fail_rate"]), "REG009"),
    (lambda r: r.update(guardrails=[g for g in r["guardrails"] if not g["metric"].startswith("review")]), "REG009"),
    (lambda r: r.update(analysis_owner=r["sponsor"]), "REG010"),
])
def test_each_rule_fires_alone(reviewed, change, rule):
    reg = copy.deepcopy(reviewed)
    change(reg)
    assert rules(reg) == {rule}


def test_power_is_recomputed_and_the_assignment_list_is_bound(reviewed):
    assert rules(reviewed, power=reviewed["power"]["power"] - 0.10) == {"REG007"}
    assert rules(reviewed, sha="0" * 64) == {"REG004"}


def test_a_registration_changed_after_it_was_frozen_fails():
    raw = (DATA_DIR / "prereg" / "prereg-reviewed.json").read_bytes()
    frozen = json.loads((DATA_DIR / "prereg" / "frozen.json").read_text(encoding="utf-8"))
    assert check_frozen(raw, frozen, "adoption-pilot-2027", "2027-03-01") == []
    changed = raw.replace(b'"metric": "change_lead_time"', b'"metric": "change_fail_rate"', 1)
    assert changed != raw
    assert [f.rule for f in check_frozen(changed, frozen, "adoption-pilot-2027", "2027-03-01")] == ["REG011"]
    assert [f.rule for f in check_frozen(raw, frozen, "another-pilot", "2027-03-01")] == ["REG011"]
    late = dict(frozen, frozen_on="2027-03-02")
    assert [f.rule for f in check_frozen(raw, late, "adoption-pilot-2027", "2027-03-01")] == ["REG011"]


def test_interim_looks_with_alpha_spending_are_allowed(reviewed):
    reg = copy.deepcopy(reviewed)
    reg["analysis"]["interim_looks"] = "two looks with O'Brien-Fleming alpha spending"
    assert rules(reg) == set()


# --- TODO 1: power by simulation for task-level designs ------------------------------------------------------------

def test_with_no_effect_power_is_the_false_alarm_rate():
    p = simulate_power("D3", COMPS, SIZES, 1.0, reps=2000)
    assert 0.02 <= p <= 0.08
    assert simulate_power("D3", COMPS, SIZES, 1.0, reps=2000, test="sign") <= 0.08


def test_power_belongs_to_a_test():
    assert simulate_power("D3", COMPS, SIZES, 0.80, test="sign") < simulate_power("D3", COMPS, SIZES, 0.80)
    with pytest.raises(ValueError):
        simulate_power("D1", COMPS, SIZES, 0.80, test="sign")


def test_power_grows_with_effect_and_duration_and_is_seeded():
    small = simulate_power("D3", COMPS, SIZES, 0.90)
    large = simulate_power("D3", COMPS, SIZES, 0.75)
    assert small < large and large > 0.9
    assert simulate_power("D3", COMPS, SIZES, 0.85, weeks=8) < simulate_power("D3", COMPS, SIZES, 0.85, weeks=26)
    assert simulate_power("D3", COMPS, SIZES, 0.85) == simulate_power("D3", COMPS, SIZES, 0.85)


def test_contamination_costs_power_and_all_four_teams_beat_two():
    clean = simulate_power("D3", COMPS, SIZES, 0.85, assumptions={"contamination_task": 0.0})
    dirty = simulate_power("D3", COMPS, SIZES, 0.85, assumptions={"contamination_task": 0.5})
    assert dirty < clean
    assert simulate_power("D4", COMPS, SIZES, 0.85) > simulate_power("D3", COMPS, SIZES, 0.85)


def test_task_level_design_beats_two_teams_against_two():
    assert simulate_power("D3", COMPS, SIZES, 0.80) > simulate_power("D1", COMPS, SIZES, 0.80) + 0.4
    assert math.isclose(simulate_power("D1", COMPS, SIZES, 0.80), simulate_power("D1", COMPS, SIZES, 0.80))
