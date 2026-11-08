"""Specification tests for TODO 4 (check_adr) and TODO 5 (check_threat_model)."""

from archscore.checks import check_adr, check_threat_model
from archscore.docs import parse_adr, parse_threat_model
from archscore.model import Catalogue, Driver, Option

CAT = Catalogue("t", "sam.o", ("sam.o", "lena.k"), {"D1": "x", "D3": "y"},
                (Driver("ESC-N01", "nfr", "human-ai", "t", 3, True, "s"),
                 Driver("CON-1", "constraint", "constraint", "t", 3, False, "s")))

GOOD_ADR = """# ADR-001 — Something
Status: accepted
Date: 2026-11-25
Decided by: sam.o (architect)
Links: D3, CON-1
Revisit when: the team doubles.

## Context
Why.

## Options considered
### Option A — One
### Option B — Two

## Decision
Option A.

## Consequences
Some.

## Rejected alternatives
### Option B — Two
Rejected because: it needs five pipelines for a rota of eight engineers.
"""


def codes(findings):
    return [f.code for f in findings]


def adr(text):
    return check_adr(parse_adr(text), CAT)


# ------------------------------------------------------------ TODO 4: check_adr

def test_a_complete_adr_has_no_findings():
    assert adr(GOOD_ADR) == []


def test_item_is_the_adr_id():
    found = adr(GOOD_ADR.replace("Status: accepted", "Status: done"))
    assert [(f.code, f.item) for f in found] == [("ADR002", "ADR-001")]


def test_missing_fields_one_finding_each_in_field_order():
    text = GOOD_ADR.replace("Date: 2026-11-25\n", "").replace("Revisit when: the team doubles.\n", "")
    assert [f.message for f in adr(text)] == ["missing field 'Date'", "missing field 'Revisit when'"]


def test_empty_field_counts_as_missing():
    assert codes(adr(GOOD_ADR.replace("Date: 2026-11-25", "Date:"))) == ["ADR001"]


def test_status_is_compared_in_lower_case():
    assert adr(GOOD_ADR.replace("Status: accepted", "Status: Accepted")) == []


def test_missing_section():
    text = GOOD_ADR.replace("## Consequences\nSome.\n", "")
    assert codes(adr(text)) == ["ADR003"]


def test_one_option_is_not_a_choice():
    text = GOOD_ADR.replace("### Option B — Two\n\n## Decision", "\n## Decision")
    assert "ADR004" in codes(adr(text))


def test_every_option_must_be_chosen_or_rejected():
    text = GOOD_ADR.replace("### Option B — Two\n\n## Decision", "### Option B — Two\n### Option C — Three\n\n## Decision")
    found = adr(text)
    assert [(f.code, f.message) for f in found] == [("ADR005", "Option C is neither chosen nor rejected")]


def test_a_rejection_needs_a_real_reason():
    text = GOOD_ADR.replace("it needs five pipelines for a rota of eight engineers.", "too complex for now.")
    found = adr(text)
    assert codes(found) == ["ADR006"] and "4 words" in found[0].message


def test_a_rejected_heading_without_a_reason_line_is_adr006():
    text = GOOD_ADR.replace("Rejected because: it needs five pipelines for a rota of eight engineers.\n", "")
    assert codes(adr(text)) == ["ADR006"]


def test_unknown_links_are_reported_each():
    found = adr(GOOD_ADR.replace("Links: D3, CON-1", "Links: D3, D10, ESC-N11"))
    assert [f.message for f in found] == ["unknown ID 'D10'", "unknown ID 'ESC-N11'"]


def test_an_adr_must_link_to_the_prd():
    # CON-1 is known but is not a PRD decision or NFR; D12 matches neither the catalogue nor the PRD pattern.
    found = adr(GOOD_ADR.replace("Links: D3, CON-1", "Links: CON-1"))
    assert codes(found) == ["ADR008"]
    assert codes(adr(GOOD_ADR.replace("Links: D3, CON-1", "Links: CON-1, D12"))) == ["ADR007", "ADR008"]


def test_decider_must_be_a_named_person():
    assert codes(adr(GOOD_ADR.replace("Decided by: sam.o (architect)", "Decided by: relay-architect-agent"))) == ["ADR009"]
    assert adr(GOOD_ADR.replace("Decided by: sam.o (architect)", "Decided by: lena.k")) == []


def test_superseded_needs_a_successor():
    text = GOOD_ADR.replace("Status: accepted", "Status: superseded")
    assert codes(adr(text)) == ["ADR010"]
    assert adr(text.replace("Status: superseded", "Status: superseded\nSuperseded by: ADR-009")) == []


# ------------------------------------------------------------ TODO 5: check_threat_model

OPT = Option("A", "A", "", (), (), {"TB1": "edge", "TB2": "model"}, (), {})

GOOD_TM = """# Threat model — Option A
Option: A
Author: priya.n
Reviewed by: aisha.r

## Diagram

```mermaid
flowchart LR
    C -- "TB1" --> W
    W -- "TB2" --> M
```

## Threats

| # | Boundary | STRIDE | Threat | Control | Evidence |
| ---: | --- | --- | --- | --- | --- |
| 1 | TB1 | S | Stolen token | Hashes | test_a |
| 2 | TB2 | T/I | Injection | Suggestions only | test_b |
| 3 | none | E | Shared role | Fitness tests | residual risk, owner sam.o |
"""


def tm(text):
    return check_threat_model(parse_threat_model(text), OPT)


def test_a_complete_threat_model_has_no_findings():
    assert tm(GOOD_TM) == []


def test_boundary_without_a_threat():
    found = tm(GOOD_TM.replace("| 2 | TB2 | T/I |", "| 2 | TB1 | T/I |"))
    assert [(f.code, f.item) for f in found] == [("TM001", "TM-A")] and "TB2" in found[0].message


def test_unknown_boundary():
    found = tm(GOOD_TM.replace("| 3 | none |", "| 3 | TB9 |"))
    assert codes(found) == ["TM002"] and "threat 3" in found[0].message


def test_stride_letters():
    assert codes(tm(GOOD_TM.replace("| T/I |", "| T, X |"))) == ["TM003"]
    assert codes(tm(GOOD_TM.replace("| T/I |", "| Tampering |"))) == ["TM003"]
    assert codes(tm(GOOD_TM.replace("| T/I |", "|  |"))) == ["TM003"]
    assert tm(GOOD_TM.replace("| T/I |", "| T, I |")) == []


def test_control_and_evidence():
    assert codes(tm(GOOD_TM.replace("| Hashes | test_a |", "|  | test_a |"))) == ["TM004"]
    assert codes(tm(GOOD_TM.replace("| Hashes | test_a |", "| Hashes |  |"))) == ["TM005"]


def test_diagram_must_label_every_boundary():
    found = tm(GOOD_TM.replace('    W -- "TB2" --> M\n', ""))
    assert [f.message for f in found] == ["diagram does not label TB2"]
    no_diagram = GOOD_TM[:GOOD_TM.index("```mermaid")] + GOOD_TM[GOOD_TM.index("## Threats"):]
    assert [f.message for f in tm(no_diagram)] == ["no diagram"]


def test_reviewer_must_be_someone_else():
    assert codes(tm(GOOD_TM.replace("Reviewed by: aisha.r", "Reviewed by: priya.n"))) == ["TM007"]
    assert codes(tm(GOOD_TM.replace("Reviewed by: aisha.r", "Reviewed by:"))) == ["TM007"]
