"""Golden tests: every number Chapter 14 quotes from Lab 14.2, and the data's reproducibility."""

import json
import subprocess
import sys

from conftest import DATA_DIR, LAB_ROOT

from govpack.report import (render_aiact, render_claims, render_dpia, render_licenses, render_matrix_report,
                            render_pack)


def test_permission_matrix():
    assert "Identities: 5 people, 7 agents; permissions in the catalogue: 17; findings: 6" in render_matrix_report(True)
    text = render_matrix_report(True)
    for line in ("| GOV001 | coding-session | agent holds github:pr:approve |",
                 "| GOV001 | detection-automation | agent holds ops:killswitch:restore |",
                 "| GOV003 | aws:break-glass:approve | held by 1 person(s): sam.o |",
                 "| GOV002 | eval-harvester | no accountable owner |"):
        assert line in text
    assert "findings: 0" in render_matrix_report(False)


def test_dpia():
    assert "Flows: 5; risks: 4; findings: 11 (DP001 1, DP002 1, DP003 2, DP004 1, DP005 1, DP006 2, DP007 2, DP008 1)" \
        in render_dpia(True)
    assert "Flows: 5; risks: 4; findings: 0" in render_dpia(False)


def test_licences():
    text = render_licenses()
    assert "Components: 11; allow 7, review 3, deny 1" in text
    assert "| logscrub | proposed dependency | AGPL-3.0-or-later | deny |" in text


def test_ai_act_classification():
    text = render_aiact()
    assert "Tiers: prohibited 1, high-risk 1, transparency 1, minimal 2, outside the definition 1" in text
    assert "| F4 Smart assignment | proposed | high-risk | provider |" in text
    assert "| F6 Team mood insights | requested by a prospect | prohibited | provider | Art. 5(1)(f): emotion "         "recognition from biometric data (voice) in the workplace | 2025-02-02 |" in text
    assert "| 2027-12-02 |" in text.split("F4 Smart assignment")[1].splitlines()[0]
    assert "| F3 Help-centre assistant | planned | transparency | provider | Art. 50(1) and Art. 50(2) | 2026-08-02 |"         in text
    assert "Regulation (EU) 2026/1744 (Digital Omnibus on AI) of 8 July 2026" in text


def test_claims():
    assert "# Overclaims in pack-draft.md: 7" in render_claims(True)
    assert "# Overclaims in pack-reviewed.md: 0" in render_claims(False)


def test_the_assembled_pack_states_its_limits_and_overclaims_nothing():
    pack = render_pack()
    assert pack.count("It is not a compliance claim") == 1 and "Overclaims in pack-reviewed.md: 0" in pack


def test_generator_reproduces_committed_data(tmp_path):
    before = {p.relative_to(DATA_DIR).as_posix(): p.read_bytes() for p in DATA_DIR.rglob("*") if p.is_file()}
    subprocess.run([sys.executable, str(LAB_ROOT / "scripts" / "generate_data.py"), "--out", str(tmp_path)],
                   check=True, capture_output=True)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert after == before


def test_every_json_file_is_labelled_and_the_agents_match_relay_4_23_0():
    for path in sorted(DATA_DIR.rglob("*.json")):
        assert "GENERATED" in json.loads(path.read_text(encoding="utf-8"))["label"], path.name
    registry = LAB_ROOT.parent / "L14.1-agent-identity-kill-switch" / "relay-repo" / "governance" / "agents.json"
    if registry.is_file():
        agents = {a["agent_id"]: a["owner"] for a in json.loads(registry.read_text(encoding="utf-8"))["agents"]}
        grants = json.loads((DATA_DIR / "matrix" / "grants-reviewed.json").read_text(encoding="utf-8"))
        ours = {i["id"]: i["owner"] for i in grants["identities"] if i["kind"] == "agent"}
        assert {k: v for k, v in ours.items() if k != "detection-automation"} == agents


def test_exercise_8_a_reply_drafting_agent():
    """Locks book/answers/ch14-answers.md, Exercise 8: drafting is Art. 50(2); unreviewed sending adds 50(1)."""
    from govpack import load_json
    from govpack.aiact import classify_feature
    dates = load_json(DATA_DIR / "aiact" / "dates.json")["dates"]
    f = {"id": "FX", "ai_system": True, "placed_on_market": True, "prohibited_practice": None, "annex_iii_area": None,
         "profiles_people": False, "narrow_procedural_task": False, "interacts_with_people": False,
         "generates_synthetic_content": True, "emotion_recognition": False}
    reviewed = classify_feature(f, dates)
    unreviewed = classify_feature({**f, "interacts_with_people": True}, dates)
    assert (reviewed.tier, reviewed.basis) == ("transparency", "Art. 50(2)")
    assert (unreviewed.tier, unreviewed.basis) == ("transparency", "Art. 50(1) and Art. 50(2)")
