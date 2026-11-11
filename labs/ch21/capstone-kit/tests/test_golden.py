"""Golden tests: every number Chapter 21 quotes from the capstone kit."""

import json

from conftest import DATA_DIR

from capstone.report import (render_ceilings, render_check, render_defense, render_fixtures, render_redteam,
                             render_remains, render_score, render_tracks)

RELAY = "data/packs/relay-b-4.31.0"


def test_tracks():
    text = render_tracks()
    for line in ("- A Production service: 16 required kinds of evidence, 6 rubric dimensions",
                 "- B Bounded agent platform: 19 required kinds of evidence, 6 rubric dimensions",
                 "- C Enterprise adoption: 14 required kinds of evidence, 6 rubric dimensions",
                 "- D Agentic security assessment: 10 required kinds of evidence, 6 rubric dimensions (Threat "
                 "model 10%, Attack-class coverage and findings 20%, Hardening effectiveness 20%, Verification of "
                 "defences 20%, Detection and response 15%, Judgement and communication 15%)"):
        assert line in text, line


def test_fixtures_table():
    text = render_fixtures()
    rows = [line for line in text.splitlines() if line.startswith("| ") and "Fixture" not in line and "---" not in line]
    assert len(rows) == 30
    assert sum("| yes |" in r for r in rows) == 4
    for line in ("| a-fail-overclaim | A | no | EV004 x2, EV011 |", "| a-fail-tampered | A | no | EV003 |",
                 "| c-fail-operating-model | C | no | EV011 x7 |", "| c-fail-roi | C | no | EV011 x4 |",
                 "| d-fail-attack-text | D | no | EV012 |", "| d-fail-shared-domain | D | no | EV011 |",
                 "| d-fail-drill | D | no | EV006, EV011 |", "| b-fail-merge-tool | B | no | EV011 |",
                 "| a-fail-stale | A | no | EV008 x2 |", "| a-fail-file-release | A | no | EV008 |",
                 "| a-fail-no-release | A | no | EV008 |", "| a-fail-open-label | A | no | EV001 |"):
        assert line in text, line


def test_relay_sample_pack():
    text, code = render_check(RELAY)
    assert code == 1
    for line in (
            "# Evidence pack: relay (sample), track B, Relay spec-to-PR helper 4.31.0, as of 2027-07-26",
            "Items: 22 (modelled 5, verified 17)",
            "Required kinds of evidence: 19: ok 12, with blocking findings 2, missing 5",
            "Acceptance criteria with usable evidence: 6 of 8",
            "Findings: 11 blocking, 10 warnings (EV001 5, EV006 2, EV008 2, EV010 1, EV011 1)",
            "- EV008 [block] R11: evidence for 4.29.0, the pack defends 4.31.0",
            "- EV013 [warn] R11: 10 of 10 counted controls' deployment records are generated, not observed",
            "- EV008 [block] R19: evidence for 4.30.0, the pack defends 4.31.0",
            "- EV011 [block] R19: decision 'not ready' on 2027-03-19 (rows not met: 4, 7, 8, 9, 12, 14, 16)",
            "- EV001 [block] spec: no item for 'Spec package: scope, acceptance criteria and evidence plan'",
            "- EV001 [block] red-team: no item for 'Red-team exchange log, findings fixed or formally blocked'",
            "- EV001 [block] signature: no item for 'Signature and verification records for released artefacts'",
            "- EV001 [block] disclosure: no item for 'AI-use disclosure'",
            "- EV001 [block] safety-case: no item for 'Safety and security case'",
            "- EV006 [block] B-AC06: no usable evidence (cites R11)",
            "- EV006 [block] B-AC08: no usable evidence (cites R19)",
            "- EV010 [block] team: no members and no contribution statements",
            "- EV009 [warn] OI-06: due 2027-04-16 (sam.o), no completion recorded: alert on dead agent jobs",
            "- EV009 [warn] OI-08: due 2027-07-22 (sam.o), no completion recorded: live rerun of the design "
            "comparison (ADR-027 review)",
            "- EV009 [warn] OI-10: no date: person-proof signature verifier"):
        assert line in text, line
    assert text.count("EV009 [warn]") == 9
    assert sum(1 for line in text.splitlines() if "no completion recorded" in line) == 8


def test_relay_ceilings():
    text = render_ceilings(RELAY)
    for line in ("| Engineering correctness | 20% | 59 | spec missing |",
                 "| Security | 20% | 59 | adversarial has blocking findings; red-team missing; signature missing |",
                 "| Verification | 20% | 74 | adversarial has blocking findings |",
                 "| Operations | 15% | 74 | readiness has blocking findings |",
                 "| Agent reliability | 10% | 100 | - |",
                 "| Traceability and judgement | 15% | 59 | safety-case missing; disclosure missing |",
                 "Highest total the evidence allows: 68.4 (Needs work)"):
        assert line in text, line


def test_scores():
    text, code = render_score("data/scores/kestrel-a.json")
    assert code == 0 and "Total: 90.6; level: Excellent; outcome: pass" in text
    text, _ = render_score("data/scores/kestrel-a-unstated.json")
    for line in ("Total: 89.0; level: Acceptable; outcome: pass",
                 "- RB004 the panel found 1 unstated limitation(s): total 90.6 capped at 89",
                 "| k.ade | Acceptable | met | - |",
                 "| k.cy | Fail | not met | RB006 could not explain and modify the part drawn |"):
        assert line in text, line
    text, code = render_score("data/scores/kestrel-a-open-high.json")
    assert code == 1
    for line in ("| security | 20% | 88 | 74 | 74 | red-team has blocking findings; RB002 A06 has blocking findings |",
                 "Total: 87.8; level: Fail; outcome: fail",
                 "- RB005 security gate: open critical or high red-team finding in A06",
                 "- RB008 security gate: red-team blocked",
                 "- RB009 the pack has 1 blocking finding(s): Gate G6 not met until they are gone",
                 "| k.ade | Fail | not met | - |"):
        assert line in text, line
    text, _ = render_score("data/scores/kestrel-a-uncited.json")
    for line in ("| operations | 15% | 85 | 0 | 0 | RB001 no evidence cited |",
                 "| security | 20% | 88 | 59 | 59 | RB003 A99 is not in the pack |",
                 "Total: 72.0; level: Needs work; outcome: conditional pass: five working days to remediate, then "
                 "re-scored", "| k.ade | Needs work | not met | - |"):
        assert line in text, line


def test_redteam_logs():
    text, code = render_redteam("data/redteam/osprey-on-kestrel.json")
    assert code == 0
    assert "Findings logged: 3; valid: 3; open critical or high: 0" in text
    assert "Credit: attacking team 3, defending team 2" in text
    text, code = render_redteam("data/redteam/osprey-on-kestrel-bad.json")
    assert code == 1
    for line in ("Findings logged: 4; valid: 1; open critical or high: 1",
                 "- RT001 [block] RT-01: target 'kestrel-production' is outside the written scope",
                 "- RT006 [block] RT-02: field(s) payload are not in the template",
                 "- RT007 [block] RT-04: marked fixed without a pull request and a re-test that blocked it"):
        assert line in text, line


def test_defense_draw():
    panel = json.loads((DATA_DIR / "defense" / "kestrel-panel.json").read_text(encoding="utf-8"))
    text = render_defense("data/defense/kestrel-statements.json", panel["seed"], panel["seed_commitment"])
    for line in ("## k.ade: P02 the AI summary step and its fallback (written by k.bo; agent-assisted)",
                 "3. With an agent, make this change and verify it: fall back after 5 s instead of 10 s",
                 "## k.bo: P06 ADR-001 and the threat model (written by k.ade, k.cy)",
                 "## k.cy: P07 the release workflow and admission check (written by k.bo; agent-assisted)",
                 "Evidence walk-through: A-AC02, A-AC03"):
        assert line in text, line


def test_what_remains():
    text = render_remains("2027-07-26", None)
    for line in ("Open items: 63; date passed, no completion recorded 13; due later 4; no date recorded 46; "
                 "no owner recorded 25",
                 "By capstone track: A 26, B 32, C 12, D 17"):
        assert line in text, line
    expect = {"A": "Open items: 26; date passed, no completion recorded 7; due later 2; no date recorded 17; "
                   "no owner recorded 11",
              "B": "Open items: 32; date passed, no completion recorded 8; due later 2; no date recorded 22; "
                   "no owner recorded 13",
              "C": "Open items: 12; date passed, no completion recorded 0; due later 0; no date recorded 12; "
                   "no owner recorded 5",
              "D": "Open items: 17; date passed, no completion recorded 3; due later 0; no date recorded 14; "
                   "no owner recorded 6"}
    for t, line in expect.items():
        assert line in render_remains("2027-07-26", t), t


def test_table_21_17_past_dates():
    from capstone.remains import view
    past = [(r["chapter"], r.get("owner"), r["due"]) for r in view("2027-07-26")["rows"]
            if r["status"] == "date passed, no completion recorded"]
    assert sorted(past, key=lambda x: (x[2], x[0])) == [
        (12, "priya.n", "2027-03-31"), (16, "sam.o", "2027-03-31"), (18, "sam.o", "2027-04-16"),
        (16, "aisha.r", "2027-04-30"), (16, None, "2027-04-30"),
        (18, "priya.n", "2027-04-30"), (18, "sam.o", "2027-04-30"), (12, "aisha.r", "2027-05-31"),
        (18, "sam.o", "2027-05-31"), (18, "aisha.r with sam.o", "2027-05-31"), (18, "sam.o", "2027-05-31"),
        (18, "priya.n", "2027-06-30"), (10, "sam.o", "2027-07-22")]


def test_relay_slos_cover_the_api_and_triage_only():
    from conftest import REPO
    slos = json.loads((REPO / "labs/relay-baselines/4.31.0/relay-repo/docs/slo/slos.json").read_text(
        encoding="utf-8"))["slos"]
    ids = [s["slo_id"] for s in slos]
    assert len(ids) == 5 and all(i.startswith(("SLO-API-", "SLO-TRIAGE-")) for i in ids)
