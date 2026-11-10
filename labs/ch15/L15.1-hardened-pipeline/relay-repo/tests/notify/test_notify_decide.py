"""The send decision, by example (PR notify-2; ADR-018). One test per rule in relay.notify.decide's docstring.

Each expected value was worked out by reading the legacy module, not by running the new code.
"""

from datetime import date, datetime

from relay.notify.decide import Prefs, decide, parse_muted

MARKED = Prefs(frozenset(), date(2026, 12, 1))  # a spam mark made on 1 December, at any time of day


def test_both_legacy_list_formats_any_case_and_blanks_parse_alike():
    assert parse_muted("Comment;MENTION") == parse_muted("comment, mention,") == frozenset({"comment", "mention"})
    assert parse_muted(None) == parse_muted("") == frozenset()


def test_a_spam_mark_suppresses_through_day_29_and_expires_at_midnight_utc_on_day_30():
    assert decide(MARKED, "comment", datetime(2026, 12, 30, 23, 59)).reason == "spam_mark"
    assert decide(MARKED, "comment", datetime(2026, 12, 31, 0, 0)).send is True


def test_a_spam_mark_suppresses_security_notices_too():
    # Characterized, not endorsed: the legacy code checked the spam mark before the type.
    assert decide(MARKED, "security", datetime(2026, 12, 2)).reason == "spam_mark"


def test_security_notices_cannot_be_muted():
    assert decide(Prefs(frozenset({"all", "security"})), "security", datetime(2026, 12, 2)).send is True


def test_all_mutes_every_other_type_including_unknown_ones():
    assert decide(Prefs(frozenset({"all"})), "billing_alert", datetime(2026, 12, 2)).reason == "muted_all"


def test_an_unknown_type_is_sent_unless_all_is_muted():
    assert decide(Prefs(frozenset({"comment"})), "billing_alert", datetime(2026, 12, 2)).send is True
