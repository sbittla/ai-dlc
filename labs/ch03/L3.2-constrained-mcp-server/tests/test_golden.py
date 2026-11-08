"""Golden tests: every number Chapter 3 quotes from this lab."""

from conftest import DATA_DIR

from relaymcp import report


def test_replay_summary_matches_chapter_3():
    text = report.render(DATA_DIR)
    for row in ("Templates: 6 · row cap 50 · request cap 2048 bytes",
                "| Requests | 26 |",
                "| Legitimate, answered | 8 of 8 |",
                "| Attacks refused | 16 of 18 |",
                "| Attacks answered harmlessly (bound as data) | 2 (A07, A08) |",
                "| Rows returned, total | 43 |",
                "| Values redacted | 12 |",
                "| Audit entries | 26 |",
                "| Responses containing an email, name or hash from the database | 0 |",
                "| Tables unchanged after the run | yes (80 tasks) |",
                "| unknown_template | 2 |",
                "| bad_type | 3 |",
                "Template lint: 0 problem(s)"):
        assert row in text, row


def test_replay_rows_quoted_in_the_chapter():
    text = report.render(DATA_DIR)
    assert "| L05 | legitimate | who works on a project (PII redacted) | ok | 6 |  | 12 |" in text
    assert "| L07 | legitimate | first page of a project | ok | 5 | yes | 0 |" in text
    assert "| A08 | attack | LIKE wildcard to match everything | ok | 4 |  | 0 |" in text


def test_show_a07_prints_the_bound_value():
    text = report.show(DATA_DIR, "A07")
    assert 'Bound parameters: {"project_id": 1, "title_contains": "%\' UNION SELECT email FROM users --%"}' in text
    assert '"rows": []' in text


def test_show_refused_request_never_reaches_sql():
    assert "Refused before any SQL ran: unknown_template" in report.show(DATA_DIR, "A01")
