"""Specification tests for Lab 4.1's checker, on inputs small enough to check by hand."""

import pytest

from reqcheck import checks, prd as prdmod
from reqcheck.prd import Criterion, Requirement, SourceRef
from reqcheck.sources import Source

SOURCES = {
    "INT-9": Source("INT-9", "**Ana:** If a P1 sits for fifteen minutes,\n> it should go to the shift lead.\n", ()),
}


def codes(findings):
    return [f.code for f in findings]


# ------------------------------------------------------------ TODO 1: provenance

def test_no_source_is_one_rq001():
    assert codes(checks.check_provenance("R1", [], SOURCES, 5)) == ["RQ001"]


def test_unknown_document_is_rq002_only():
    refs = [SourceRef("INT-404", "If a P1 sits for fifteen minutes")]
    assert codes(checks.check_provenance("R1", refs, SOURCES, 5)) == ["RQ002"]


def test_verbatim_quote_passes_across_line_breaks_and_blockquotes():
    refs = [SourceRef("INT-9", "fifteen minutes, it should go to the shift lead.")]
    assert checks.check_provenance("R1", refs, SOURCES, 5) == []


@pytest.mark.parametrize("quote", [
    "If a P1 sits for 15 minutes",            # a number for a word is a paraphrase
    "if a P1 sits for fifteen minutes",        # case is part of the words
    "it should go to the workspace Owner",     # plausible, never said
])
def test_paraphrase_is_rq003(quote):
    assert codes(checks.check_provenance("R1", [SourceRef("INT-9", quote)], SOURCES, 5)) == ["RQ003"]


def test_short_quote_that_is_verbatim_is_rq004():
    found = checks.check_provenance("R1", [SourceRef("INT-9", "P1 sits")], SOURCES, 5)
    assert codes(found) == ["RQ004"] and "2-word" in found[0].message


def test_each_ref_is_checked():
    refs = [SourceRef("INT-9", "the shift lead"), SourceRef("NOPE", "x"), SourceRef("INT-9", "never said at all here")]
    assert codes(checks.check_provenance("R1", refs, SOURCES, 5)) == ["RQ004", "RQ002", "RQ003"]


# ------------------------------------------------------------ TODO 2: vague terms

TERMS = ("fast", "as needed", "etc.", "and/or", "simple", "need")


def test_vague_terms_found_in_order_of_appearance():
    found = checks.find_vague_terms("R1", "Simple rules, notify and/or page as needed, etc.", TERMS)
    assert [f.message for f in found] == ["vague term 'simple'", "vague term 'and/or'",
                                          "vague term 'as needed'", "vague term 'etc.'"]
    assert set(codes(found)) == {"RQ010"}


def test_vague_terms_match_whole_words_only():
    assert checks.find_vague_terms("R1", "Breakfast is served; the needle moves.", TERMS) == []


def test_each_vague_term_reported_once():
    assert len(checks.find_vague_terms("R1", "fast, FAST and fast", TERMS)) == 1


# ------------------------------------------------------------ TODO 3: criteria

def req(rid="R1", criteria=(), **kw):
    return Requirement(rid, "t", criteria=[Criterion(i, t) for i, t in criteria], **kw)


def test_no_criteria_is_rq020():
    assert codes(checks.check_criteria(req())) == ["RQ020"]


def test_given_when_then_passes():
    r = req(criteria=[("AC1", "Given a P1 task, when 10 minutes pass, then the first step fires."),
                      ("AC2", "given an Admin\nwhen they save\nthen it saves")])
    assert checks.check_criteria(r) == []


@pytest.mark.parametrize("text", [
    "Escalation works after 30 minutes.",                 # no structure
    "When 10 minutes pass, then the step fires.",          # no Given
    "Given a P1 task, then the step fires when it is late.",  # Then before When
    "Given a P1 task, when 10 minutes pass, then",         # empty Then
])
def test_not_gwt_is_rq021_on_the_criterion(text):
    found = checks.check_criteria(req(criteria=[("AC9", text)]))
    assert codes(found) == ["RQ021"] and found[0].item == "AC9"


# ------------------------------------------------------------ TODO 4: contradictions

def test_same_key_different_values_is_one_rq030_per_pair():
    reqs = [req("R1", values=[("p1_minutes", "15")]), req("R2", values=[("p1_minutes", "10")]),
            req("R3", values=[("p1_minutes", "15 "), ("editors", "admins")]), req("R4", values=[("editors", "members")])]
    found = checks.find_contradictions(reqs)
    assert [(f.item, f.message) for f in found] == [
        ("R1 vs R2", "p1_minutes: 15 vs 10"),
        ("R2 vs R3", "p1_minutes: 10 vs 15"),
        ("R3 vs R4", "editors: admins vs members"),
    ]


def test_agreeing_values_are_not_contradictions():
    assert checks.find_contradictions([req("R1", values=[("k", "1")]), req("R2", values=[("k", "1")])]) == []


# ------------------------------------------------------------ TODO 5: traceability

TRACE_PRD = """# PRD — t

## Goals

### G1 — measured
Measure: m
Baseline: b
Target: t

### G2 — half-framed
Measure: m

### G3 — orphan
Measure: m
Baseline: b
Target: t

## Decisions

### D1 — d
Decision: x

## Requirements

### R1 — ok
Goal: G1
Decision: D1
Criteria:
- AC1: Given a, when b, then c

### R2 — no goal
Decision: D9
Depends on: R1, R7
Criteria:
- AC1: Given a, when b, then c

### R3 — unknown goal
Goal: G2, G8
"""


def test_traceability_findings_in_specified_order():
    found = checks.check_traceability(prdmod.parse(TRACE_PRD))
    assert [(f.code, f.item, f.message) for f in found] == [
        ("RQ064", "AC1", "identifier used more than once"),
        ("RQ062", "G2", "missing baseline, target"),
        ("RQ061", "R2", "no Goal"),
        ("RQ063", "R2", "decision D9 is not recorded"),
        ("RQ065", "R2", "depends on unknown R7"),
        ("RQ061", "R3", "unknown goal G8"),
        ("RQ060", "G3", "no requirement cites this goal"),
    ]


# ------------------------------------------------------------ provided checks

def test_parser_reads_every_field():
    p = prdmod.parse("""# PRD — x
Version: 1.0
Status: approved
Product owner: lena.k
Approved by: lena.k
Approved on: 2026-11-19

## Requirements

### ESC-R01 — t
Kind: nfr
Category: Security
Goal: G1, G2
Source: INT-1 | a quote | with a bar
Statement: Relay must not do x.
Value: k = 1, 2
Introduces: task_priority
Depends on: ESC-R02
Criteria:
- ESC-AC01: Given a, when b, then c
- ESC-AC02: Given d, when e, then f
""")
    r = p.requirements[0]
    assert (p.version, p.status, p.approved_by, p.approved_on) == ("1.0", "approved", "lena.k", "2026-11-19")
    assert (r.kind, r.category, r.goals, r.values) == ("nfr", "security", ["G1", "G2"], [("k", "1, 2")])
    assert r.sources == [SourceRef("INT-1", "a quote | with a bar")]
    assert [c.id for c in r.criteria] == ["ESC-AC01", "ESC-AC02"] and r.depends_on == ["ESC-R02"]


def test_approval_needs_the_named_product_owner():
    def approval(**kw):
        p = prdmod.PRD(status="approved", product_owner="lena.k", approved_by="lena.k", approved_on="2026-11-19")
        for k, v in kw.items():
            setattr(p, k, v)
        return checks.check_approval(p)

    assert approval() == []
    assert codes(approval(status="draft")) == ["RQ080"]
    assert "not the product owner" in approval(approved_by="sam.o")[0].message
    assert "agent" in approval(approved_by="coding-agent", product_owner="coding-agent")[0].message
