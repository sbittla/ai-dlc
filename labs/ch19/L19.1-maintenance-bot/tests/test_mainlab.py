"""Hand-checkable tests for the TODOs, on fixtures small enough to work out on paper."""

from mainlab import incident, measure


def minute(hhmm, share, attempts=100, failures=3, accounts=50):
    return {"minute": hhmm, "new_version_share": share, "attempts": attempts, "failures": failures,
            "new_accounts": accounts}


def test_todo1_timeline_on_six_minutes():
    data = {"events": [{"at": "10:03", "what": "SD-001 pages"}],
            "minutes": [minute("10:00", 0), minute("10:01", 0, failures=5), minute("10:02", 5, failures=10),
                        minute("10:03", 100, failures=100), minute("10:04", 100, failures=100, accounts=40),
                        minute("10:05", 0)]}
    t = incident.timeline(data)
    assert (t.first_affected, t.full_from, t.restored) == ("10:02", "10:03", "10:05")
    assert (t.affected_minutes, t.full_minutes, t.failures_affected) == (3, 2, 210)
    assert t.baseline_failure_pct == 4.0 and t.accounts_during_full == 90 and t.page_to_restore_minutes == 2


def update(uid, regression=False, default_change=False, guard_visible=False, bump="patch", date="2027-01-05",
           sensitive=False):
    return {"update": uid, "regression": regression, "default_change": default_change,
            "guard_visible": guard_visible, "bump": bump, "date": date, "sensitive": sensitive}


def test_todo5_paired_counts_discordant_updates_only():
    history = [update("A"), update("B", regression=True, default_change=True, bump="minor", date="2027-05-12"),
               update("C", regression=True), update("D", regression=True, guard_visible=True, sensitive=True),
               update("E", bump="minor", date="2027-04-01")]
    p = measure.paired(history)
    assert (p.old_reached, p.new_reached, p.b, p.c) == (["B", "C", "D"], ["C"], 2, 0)
    assert p.p == 0.5 and p.stopped_by == {"guard": 1, "pinned-defaults": 1}
    assert (p.old_auto_merged, p.new_to_people) == (4, 3)
