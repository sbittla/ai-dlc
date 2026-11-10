"""The compatibility layer: legacy names over the new code, shadow reads and the rollback (PRs notify-4, notify-5)."""

from datetime import datetime, timezone

import pytest

import relay.notify as notify

NOW = datetime(2026, 12, 16, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(notify, "READ_FROM", "new")
    return notify.init(":memory:")


def test_the_legacy_functions_keep_their_names_and_results(fresh):
    notify.mute(7, ["Comment", "mention"])
    assert notify.get_prefs(7) == {"muted": ["comment", "mention"], "spam_marked_on": None}
    assert notify.should_send(7, "comment", NOW) is False and notify.should_send(7, "digest", NOW) is True
    notify.mark_spam(7, NOW)
    assert notify.get_prefs(7)["spam_marked_on"] == "2026-12-16"
    notify.clear_spam(7)
    assert notify.should_send(7, "digest", NOW) is True


def test_shadow_reads_return_the_legacy_answer_and_record_any_difference(fresh, monkeypatch):
    fresh.conn.execute("INSERT INTO notification_prefs VALUES (8, 'comment;mention', NULL)")  # not yet migrated
    monkeypatch.setattr(notify, "READ_FROM", "shadow")
    assert notify.should_send(8, "comment", NOW) is False  # the legacy table's answer
    [(user, legacy, new)] = fresh.shadow_differences
    assert (user, legacy.muted, new.muted) == (8, frozenset({"comment", "mention"}), frozenset())


def test_the_rollback_reads_the_legacy_table_which_every_write_kept_in_step(fresh, monkeypatch):
    notify.mute(9, ["digest"])
    monkeypatch.setattr(notify, "READ_FROM", "legacy")
    assert notify.should_send(9, "digest", NOW) is False


def test_an_unknown_read_mode_is_refused(fresh, monkeypatch):
    monkeypatch.setattr(notify, "READ_FROM", "both")
    with pytest.raises(ValueError):
        notify.should_send(9, "digest", NOW)


def test_the_read_mode_comes_from_the_environment_so_a_rollback_needs_no_deploy(monkeypatch):
    import importlib

    monkeypatch.setenv("RELAY_NOTIFY_READ_FROM", "legacy")
    try:
        assert importlib.reload(notify).READ_FROM == "legacy"
    finally:
        monkeypatch.delenv("RELAY_NOTIFY_READ_FROM")
        importlib.reload(notify)
    assert notify.READ_FROM != "legacy"  # without the variable, the module's default again
