"""Deploy-time migrations (4.25.0, ADR-031): one run creates or migrates every table; a second run changes nothing;
the legacy notification copy runs once; a cloud database host is refused until the adapter exists."""

import json
import sqlite3

import pytest

from relay.service import migrate
from relay.service.wsgi import ConfigError

TABLES = ["esc_activity", "esc_audit", "esc_fired", "esc_held", "esc_outbox", "esc_rules", "esc_schema",
          "esc_state", "notification_prefs", "notify_optouts", "notify_spam_marks", "rate_limit_windows",
          "tasks", "triage_jobs", "worker_heartbeats"]


def test_one_run_creates_every_table_at_the_latest_escalation_schema(tmp_path):
    summary = migrate.run(str(tmp_path / "relay.db"), env={})
    assert summary == {"esc_schema": 2, "notify_copy": "nothing to copy", "tables": TABLES}


def test_a_second_run_is_a_no_op(tmp_path):
    db = str(tmp_path / "relay.db")
    migrate.run(db, env={})
    assert migrate.run(db, env={})["tables"] == TABLES


def test_the_legacy_notification_copy_runs_once(tmp_path):
    db = str(tmp_path / "relay.db")
    migrate.run(db, env={})
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO notification_prefs VALUES (7, 'digest;mention', NULL)")
    assert migrate.run(db, env={})["notify_copy"] == "copied 1 legacy rows"
    assert migrate.run(db, env={})["notify_copy"] == "already copied"


def test_a_cloud_database_host_is_refused(tmp_path):
    with pytest.raises(ConfigError):
        migrate.run(str(tmp_path / "relay.db"), env={"RELAY_DB_HOST": "relay.cluster.internal"})


def test_the_command_prints_one_json_line_and_exits_0(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("RELAY_DB_HOST", raising=False)
    assert migrate.main(["--db", str(tmp_path / "relay.db")]) == 0
    assert json.loads(capsys.readouterr().out)["esc_schema"] == 2


def test_the_command_exits_1_on_a_refusal(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("RELAY_DB_HOST", "relay.cluster.internal")
    assert migrate.main(["--db", str(tmp_path / "relay.db")]) == 1
    assert "migration refused: ConfigError" in capsys.readouterr().err
