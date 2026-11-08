"""The arithmetic in book/answers/ch08-answers.md (Exercises 5 and 7), checked by running the lab's code."""

from datetime import datetime, timezone

from testfirst.oracle import check_oracles

from relay.escalation import BusinessHours
from relay.escalation.hours import to_local

UTC = timezone.utc
TOKYO = BusinessHours("08:00", "17:00", "Asia/Tokyo", (1, 2, 3, 4, 5))
BERLIN = BusinessHours("06:00", "22:00", "Europe/Berlin", (1, 2, 3, 4, 5))


def due(start, minutes, hours):
    from relay.escalation.hours import add_business_minutes
    return add_business_minutes(start, minutes, hours)


def test_exercise_5a_friday_afternoon_in_tokyo():
    d = due(datetime(2026, 11, 27, 6, 30, tzinfo=UTC), 240, TOKYO)      # Friday 15:30 Tokyo
    assert (d, to_local("Asia/Tokyo", d)) == (datetime(2026, 11, 30, 1, 30, tzinfo=UTC), datetime(2026, 11, 30, 10, 30))


def test_exercise_5b_with_saturday_listed():
    six = BusinessHours("08:00", "17:00", "Asia/Tokyo", (1, 2, 3, 4, 5, 6))
    assert due(datetime(2026, 11, 27, 6, 30, tzinfo=UTC), 240, six) == datetime(2026, 11, 28, 1, 30, tzinfo=UTC)


def test_exercise_5c_berlin_across_the_spring_change():
    d = due(datetime(2027, 3, 26, 19, 30, tzinfo=UTC), 240, BERLIN)      # Friday 20:30 Berlin, UTC+1
    assert (d, to_local("Europe/Berlin", d)) == (datetime(2027, 3, 29, 6, 30, tzinfo=UTC), datetime(2027, 3, 29, 8, 30))


def test_exercise_5d_exactly_at_the_close():
    assert due(datetime(2026, 11, 30, 6, 0, tzinfo=UTC), 120, TOKYO) == datetime(2026, 11, 30, 8, 0, tzinfo=UTC)


EXERCISE_7 = '''from relay.escalation import add_business_minutes, sign, event_body
import hmac, hashlib

def test_a():
    due = add_business_minutes(start, 240, hours)
    assert due == add_business_minutes(start, 180, hours) + timedelta(minutes=60)

def test_b():
    body = event_body(event)
    assert sign(body, key) == "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()

def test_c():
    assert add_business_minutes(start, 240, hours)

def test_d():
    assert add_business_minutes(start, 240, hours) == datetime(2026, 11, 30, 1, 30, tzinfo=UTC)
'''


def test_exercise_7_oracle_findings():
    found = [(f.code, f.test) for f in check_oracles(EXERCISE_7, "exercise7.py", ("relay.escalation",))]
    assert found == [("OI01", "test_a"), ("OI03", "test_c")]
