"""SLOs, error budgets and multi-window burn-rate alerts (4.27.0, ADR-037). The policy is the Site Reliability
Workbook's table; every expected value below is worked by hand in the comment beside it."""

from pathlib import Path

import pytest

from relay.telemetry.slo import (SLO, WORKBOOK_POLICY, BurnWindow, Series, budget, burn_rate, detection_minutes,
                                 evaluate, firing, load_slos)

ROOT = Path(__file__).resolve().parent.parent
AVAIL = SLO("SLO-T", "test", 0.999)


def flat(minutes, total=100, bad=0):
    return [total - bad] * minutes, [total] * minutes


def test_the_workbook_rows_spend_2_5_and_10_percent_of_a_30_day_budget():
    # 14.4 x 60 / 43,200 = 0.02; 6 x 360 / 43,200 = 0.05; 1 x 4,320 / 43,200 = 0.10
    assert [round(row.budget_spent(30), 4) for row in WORKBOOK_POLICY] == [0.02, 0.05, 0.1]
    assert all(row.short_minutes * 12 == row.long_minutes for row in WORKBOOK_POLICY)


def test_burn_rate_is_bad_share_over_budget_share():
    assert burn_rate(2, 1000, AVAIL) == pytest.approx(2.0)  # 0.2% bad over a 0.1% budget
    assert burn_rate(0, 0, AVAIL) == 0.0


def test_detection_time_for_a_total_outage_and_for_a_partial_one():
    page_fast = WORKBOOK_POLICY[0]
    # 100% errors: the 1-hour window needs 14.4 x 0.001 = 1.44% bad, reached after 0.0144 x 60 = 0.864 minutes
    assert detection_minutes(AVAIL, page_fast, 1.0) == pytest.approx(0.864)
    # 2% errors: 0.0144 / 0.02 x 60 = 43.2 minutes
    assert detection_minutes(AVAIL, page_fast, 0.02) == pytest.approx(43.2)
    # 1% errors never reach 1.44% in the 1-hour window
    assert detection_minutes(AVAIL, page_fast, 0.01) == float("inf")


def test_windows_include_their_end_minute():
    s = Series([9, 10, 8, 10], [10, 10, 10, 10])
    assert s.window(2, 2) == (2, 20)   # minutes 1 and 2: 0 + 2 bad
    assert s.window(3, 10) == (3, 40)  # a window longer than the series covers what exists
    with pytest.raises(ValueError):
        Series([11], [10])


def test_a_25_minute_outage_at_20_percent_pages_and_resets_soon_after():
    # 600 quiet minutes, then 25 minutes at 20% errors, then 120 quiet minutes. 100 requests a minute.
    good, total = flat(600)
    g2, t2 = flat(25, bad=20)
    g3, t3 = flat(120)
    series = Series(good + g2 + g3, total + t2 + t3)
    episodes = evaluate(series, AVAIL)
    page = [e for e in episodes if e.action == "page"]
    assert len(page) == 1
    # The 1-hour window reaches 1.44% (86.4 bad of 6,000) after 5 bad minutes (100 bad): minute 600 + 4.
    assert page[0].start == 604
    # Both page rows fire. The 1-hour row's 5-minute window holds a bad minute until minute 624 + 4 = 628;
    # the 6-hour row's 30-minute window (6 x 0.1% of 3,000 = 18 bad) holds one until 624 + 29 = 653.
    assert 0 in firing(series, AVAIL, 628) and 0 not in firing(series, AVAIL, 629)
    assert page[0].end == 653 and page[0].rows == (0, 1)
    # The 3-day row tickets first: by minute 603 its window holds 80 bad of 60,400 (burn 1.32), and its 6-hour
    # short window 80 of 36,000 or fewer requests; it is still open when the series ends.
    assert [(e.action, e.start, e.end) for e in episodes] == [("ticket", 603, 744), ("page", 604, 653)]


def test_a_single_window_would_keep_paging_long_after_the_outage():
    one_window = SLO("SLO-T", "test", 0.999, policy=(BurnWindow(60, 60, 14.4, "page"),))
    good, total = flat(600)
    g2, t2 = flat(25, bad=20)
    g3, t3 = flat(120)
    page, = evaluate(Series(good + g2 + g3, total + t2 + t3), one_window)
    # 500 bad stay in the 1-hour window until enough of them leave it: below 86.4 bad needs the window to start
    # after minute 620, so the last firing minute is 620 + 59 = 679, 55 minutes after the outage ended.
    assert (page.start, page.end) == (604, 679)


def test_two_failures_in_a_quiet_hour_do_not_page_below_min_events():
    quiet = SLO("SLO-T", "test", 0.999, min_events=100)
    series = Series([0, 0, 1], [1, 1, 1])  # 2 of 3 bad
    assert firing(series, quiet, 2) == [] and firing(series, AVAIL, 2) != []


def test_budget_remaining_over_the_period():
    good, total = flat(1000, bad=0)
    good[10] -= 50  # 50 bad of 100,000: half of the 100 allowed
    status = budget(Series(good, total), AVAIL)
    assert (status.bad, status.events, round(status.remaining, 3)) == (50, 100000, 0.5)


def test_the_committed_slos_use_the_workbook_policy():
    slos = load_slos(ROOT / "docs/slo/slos.json")
    assert sorted(slos) == ["SLO-API-AVAIL", "SLO-API-LATENCY", "SLO-TRIAGE-FRESH", "SLO-TRIAGE-QUALITY",
                            "SLO-TRIAGE-SAFETY"]
    assert slos["SLO-API-AVAIL"].policy == WORKBOOK_POLICY and slos["SLO-API-AVAIL"].target == 0.999
    assert slos["SLO-API-LATENCY"].target == 0.99
    assert {r.action for r in slos["SLO-TRIAGE-QUALITY"].policy} == {"ticket"}  # AI quality never pages
    assert all(s.owner for s in slos.values())
