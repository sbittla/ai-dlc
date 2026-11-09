"""Golden tests: every number Chapter 12 quotes from Lab 12.1. A change that moves one must fail here."""

from redteam.report import render_alone, render_gate, render_incident, render_matrix, render_removeone


def test_incident():
    text = render_incident()
    assert "Contact details in the image address: 41, from 9 customers." in text
    for stamp in ("2027-02-02 09:12:00 UTC", "2027-02-02 10:48:00 UTC", "2027-02-03 08:40:00 UTC",
                  "2027-02-03 09:05:00 UTC"):
        assert stamp in text


def test_matrix_4_26_0():
    text = render_matrix("4.26.0")
    assert "Cells: 43; verified 29; failed 0; mitigating 14; absent 0." in text
    assert "Classes with one verified control: C14." in text
    assert "Classes with no verified control: none." in text
    assert "| C12 | persistence |  |  | m |  |  |  |  | V | V | V |  | 2 |" in text


def test_matrix_4_25_0():
    text = render_matrix("4.25.0")
    assert "Cells: 43; verified 6; failed 1; mitigating 0; absent 36." in text
    assert "Failed: C10 egress_domain_only (api.github.com: allowed by name)." in text
    assert "Classes with one verified control: C05, C06, C07, C11, C12, C13." in text
    assert "Classes with no verified control: C01, C02, C03, C04, C08, C09, C10, C14." in text


def test_gate():
    assert render_gate("4.26.0") == "relay-coverage-gate-v1 on 4.26.0: PASS"
    text = render_gate("4.25.0")
    assert text.startswith("relay-coverage-gate-v1 on 4.25.0: FAIL")
    assert len(text.splitlines()) == 15  # all 14 classes fall short


def test_remove_one_and_alone():
    text = render_removeone()
    for row in ("| render | C01, C02, C03, C04 | none |",
                "| tool_scope | C05, C06, C07, C08, C09, C10, C11 | none |",
                "| memory_trust | none | none |", "| memory_review | none | none |",
                "| recall_taint | C12, C13 | none |", "| judge_isolation | C14 | C14 |"):
        assert row in text
    assert "before ADR-034 added RECALL_MEMORY): C12 1 of 2, C13 1 of 2." in text
    alone = render_alone()
    assert "| tool_scope | C05, C06, C07, C08, C09, C10, C11 | 7 of 14 |" in alone
    assert "The widest single control covers 7 of 14 classes." in alone
