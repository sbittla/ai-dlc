"""TODO 1-4 on hand-written cases, plus the provided matrix checks."""

import pytest

from govpack.aiact import HIGH_RISK_DUTIES, LITERACY, classify_feature
from govpack.claims import find_overclaims
from govpack.dpia import check_dpia
from govpack.licenses import classify
from govpack.matrix import check_matrix

DATES = {"prohibited": "2025-02-02", "ai_literacy": "2025-02-02", "gpai": "2025-08-02",
         "transparency": "2026-08-02", "high-risk (Annex III)": "2026-08-02"}


def feature(**changes):
    f = {"id": "FX", "ai_system": True, "placed_on_market": True, "prohibited_practice": None, "annex_iii_area": None,
         "profiles_people": False, "narrow_procedural_task": True, "interacts_with_people": False,
         "generates_synthetic_content": False, "emotion_recognition": False}
    f.update(changes)
    return f


@pytest.mark.parametrize("changes, tier, basis, applies", [
    ({}, "minimal", "no Art. 5, Annex III or Art. 50 trigger on the team's answers", "2025-02-02"),
    ({"ai_system": False, "prohibited_practice": "x"}, "outside the definition",
     "not an AI system (Art. 3(1)) on the team's answers", None),
    ({"prohibited_practice": "Art. 5(1)(f)", "annex_iii_area": "4(b)"}, "prohibited", "Art. 5(1)(f)", "2025-02-02"),
    ({"annex_iii_area": "4(b)", "profiles_people": True}, "high-risk",
     "Annex III 4(b); it profiles people, so the Art. 6(3) exception cannot apply", "2026-08-02"),
    ({"annex_iii_area": "4(a)", "narrow_procedural_task": False}, "high-risk", "Annex III 4(a)", "2026-08-02"),
    ({"annex_iii_area": "4(a)", "interacts_with_people": True}, "transparency", "Art. 50(1)", "2026-08-02"),
    ({"interacts_with_people": True, "generates_synthetic_content": True}, "transparency",
     "Art. 50(1) and Art. 50(2)", "2026-08-02"),
])
def test_classify_feature(changes, tier, basis, applies):
    c = classify_feature(feature(**changes), DATES)
    assert (c.tier, c.basis, c.applies_from) == (tier, basis, applies)


def test_obligations_and_roles():
    assert classify_feature(feature(annex_iii_area="4(b)", profiles_people=True), DATES).obligations == \
        HIGH_RISK_DUTIES + (LITERACY,)
    assert classify_feature(feature(generates_synthetic_content=True), DATES).obligations == (
        "mark generated content as machine-generated", LITERACY)
    c = classify_feature(feature(placed_on_market=False), DATES)
    assert (c.role, c.obligations) == ("deployer", (LITERACY,))
    assert classify_feature(feature(ai_system=False), DATES).obligations == ()


POLICY = {"max_retention_days": {"trace": 30, "prompt": 0}}


def dpia(**changes):
    d = {"description": "d", "necessity_proportionality": "n", "dpo_consulted": "2027-01-08",
         "review_by": "2027-07-11",
         "flows": [{"id": "FL1", "kind": "trace", "personal_data": ["free text"], "purpose": "p",
                    "lawful_basis": "b", "retention_days": 30, "residency": "us-east-1", "processor": None,
                    "minimisation": "m"}],
         "risks": [{"id": "R1", "owner": "sam.o", "measures": ["x"]}]}
    d.update(changes)
    return d


def flow(**changes):
    return {**dpia()["flows"][0], **changes}


def found(d):
    return [(f.rule, f.subject, f.message) for f in check_dpia(d, POLICY)]


def test_a_complete_dpia_has_no_findings():
    assert found(dpia()) == []


@pytest.mark.parametrize("changes, expected", [
    ({"necessity_proportionality": ""}, [("DP001", "document", "missing necessity_proportionality")]),
    ({"risks": []}, [("DP001", "document", "missing risks")]),
    ({"flows": [flow(purpose=None, lawful_basis=None)]}, [("DP002", "FL1", "no purpose")]),
    ({"flows": [flow(lawful_basis="")]}, [("DP002", "FL1", "no lawful basis")]),
    ({"flows": [flow(retention_days=None)]}, [("DP003", "FL1", "no retention period (kept indefinitely)")]),
    ({"flows": [flow(retention_days=31)]}, [("DP003", "FL1", "retention 31 days, above the policy's 30")]),
    ({"flows": [flow(processor={"name": "model provider", "terms": None})]},
     [("DP004", "FL1", "processor model provider: data-use terms not recorded")]),
    ({"flows": [flow(residency=None)]}, [("DP005", "FL1", "no residency recorded")]),
    ({"flows": [flow(minimisation=None)]}, [("DP007", "FL1", "personal data with no minimisation measure")]),
    ({"flows": [flow(minimisation=None, personal_data=[])]}, []),
    ({"risks": [{"id": "R1", "owner": None, "measures": []}]}, [("DP006", "R1", "no owner"),
                                                                 ("DP006", "R1", "no measures")]),
    ({"dpo_consulted": None, "review_by": None}, [("DP008", "document", "no DPO consultation recorded"),
                                                  ("DP008", "document", "no review date")]),
])
def test_each_dpia_rule(changes, expected):
    assert found(dpia(**changes)) == expected


def test_dpia_findings_come_in_document_flow_risk_consultation_order():
    d = dpia(description=None, dpo_consulted=None, risks=[{"id": "R1", "owner": None, "measures": ["x"]}],
             flows=[flow(residency=None, retention_days=99)])
    assert [r for r, _, _ in found(d)] == ["DP001", "DP003", "DP005", "DP006", "DP008"]


LP = {"allow": ["MIT", "Apache-2.0", "BSD-3-Clause"], "review": ["GPL-2.0-or-later"],
      "deny_for_network_service": ["AGPL-3.0-or-later"]}


@pytest.mark.parametrize("component, expected", [
    ({"license": "MIT"}, ("allow", "MIT")),
    ({"license": "AGPL-3.0-or-later"}, ("deny", "AGPL-3.0-or-later: obligations triggered by network use")),
    ({"license": "GPL-2.0-or-later"}, ("review", "GPL-2.0-or-later: copyleft or attribution terms")),
    ({"license": "WTFPL"}, ("review", "WTFPL: not in the policy")),
    ({"license": "NOASSERTION"}, ("review", "licence not stated")),
    ({"license": None}, ("review", "no licence recorded")),
    ({"license": None, "origin": "generated code (no match)"},
     ("allow", "generated, no snippet match: record provenance")),
    ({"license": "AGPL-3.0-or-later OR MIT"}, ("allow", "MIT chosen from AGPL-3.0-or-later OR MIT")),
    ({"license": "AGPL-3.0-or-later OR GPL-2.0-or-later"},
     ("review", "GPL-2.0-or-later chosen from AGPL-3.0-or-later OR GPL-2.0-or-later")),
])
def test_classify_licence(component, expected):
    assert classify({"origin": "dependency", **component}, LP) == expected


def test_overclaims_are_found_in_order_and_negated_sentences_pass():
    text = ("# Compliant heading is ignored\n"
            "We are certified. This is not a compliance claim and is not certified.\n"
            "It guarantees uptime and is FULLY COMPLIANT. Triage is minimal-risk.\n"
            "There is no guarantee here.\n")
    assert [(o.line, o.phrase) for o in find_overclaims(text)] == [
        (2, "certified"), (3, "guarantees"), (3, "FULLY COMPLIANT"), (3, "is minimal-risk")]
    assert find_overclaims("")== []


def test_matrix_checks_are_provided():
    permissions = {"permissions": {"a": "", "b": "", "approve": ""}, "never_for_agents": ["b"],
                   "two_person": ["approve"]}
    grants = {"identities": [{"id": "p1", "kind": "person", "owner": None, "grants": ["approve"]},
                             {"id": "bot", "kind": "agent", "owner": None, "grants": ["a", "b", "z"]}]}
    assert [(f.rule, f.subject) for f in check_matrix(grants, permissions)] == [
        ("GOV001", "bot"), ("GOV002", "bot"), ("GOV004", "bot"), ("GOV003", "approve")]
