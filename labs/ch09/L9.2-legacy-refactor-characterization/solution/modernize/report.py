"""Lab 9.2's reports (provided).

    python -m modernize.report incident       # the agent's migration replayed on production-shaped data
    python -m modernize.report characterize   # the agent's rewrite and Relay 4.22.0, against the legacy module
    python -m modernize.report parallel       # five worktrees integrated in order, characterized at every step

Run from starter/ or solution/. The checks (charact, migration, parallel) come
from the folder you run in; the data and the oracle come from data/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import migration, parallel
from .paths import DATA, ORACLE, agent_module, oracle_modules, relay_notify


def accepted_classes(data: Path = DATA) -> list[str]:
    return [a["class"] for a in json.loads((data / "accepted-differences.json").read_text(encoding="utf-8"))["accepted"]]


def report_incident(data: Path = DATA) -> str:
    prod = migration.load_prod(data)
    notify = relay_notify()
    legacy, _ = oracle_modules()
    rows = prod["rows"]
    before = migration.before_prefs(rows, notify.parse_muted)

    def known(conn):
        types = set(notify.TYPES) | {"all"}
        return sum(1 for (t,) in conn.execute("SELECT type FROM notify_optouts") if t in types)

    upgrade = agent_module().upgrade  # the incident's migration, input data

    agent_db = migration.legacy_db(rows)
    upgrade(agent_db)
    agent = migration.losses(before, migration.after_prefs(agent_db, before), migration.table_exists(
        agent_db, "notification_prefs"))

    store = notify.NotifyStore(migration.legacy_db(rows))
    report = notify.migrate_legacy(store)
    reviewed = migration.losses(before, migration.after_prefs(store.conn, before),
                                migration.table_exists(store.conn, "notification_prefs"))

    legacy_conn = legacy.init(":memory:")
    legacy_conn.executemany("INSERT INTO notification_prefs VALUES (?, ?, ?)", [tuple(r) for r in rows])
    legacy_conn.commit()

    agent_code = agent_module()  # the incident's own decision, reading the tables its migration left
    agent_code._db = agent_db
    against, withheld = migration.replay(prod["events"], legacy.should_send, agent_code.should_send)
    against_r, withheld_r = migration.replay(prod["events"], legacy.should_send,
                                             lambda uid, ntype, now: notify.decide(store.prefs(uid), ntype, now).send)
    rows_out = [
        ("Users with a legacy preferences row (synthetic)", agent.users, reviewed.users),
        ("Opt-outs before (user and type pairs)", agent.optouts_before, reviewed.optouts_before),
        ("Rows in the new opt-out table", agent.optouts_after, reviewed.optouts_after),
        ('... of which name a notification type or "all"', known(agent_db), known(store.conn)),
        ("Opt-outs lost", agent.optouts_lost, reviewed.optouts_lost),
        ("Users who lost at least one opt-out", agent.users_with_optouts_lost, reviewed.users_with_optouts_lost),
        ("Spam marks before", agent.spam_marks_before, reviewed.spam_marks_before),
        ("Spam marks lost", agent.spam_marks_lost, reviewed.spam_marks_lost),
        ("Legacy table kept", "yes" if agent.legacy_table_kept else "no", "yes" if reviewed.legacy_table_kept else "no"),
        (f"Events replayed ({prod['live_from'][:16]} to {prod['live_until'][:16]} UTC)", len(prod["events"]),
         len(prod["events"])),
        ("Emails sent against a preference", against, against_r),
        ("Emails withheld that the legacy code would send", withheld, withheld_r),
    ]
    lines = ["# The incident's migration, replayed on synthetic production-shaped data", "",
             "| Measure | Agent's migration (#2291) | Relay 4.22.0's migrate_legacy |", "| --- | ---: | ---: |"]
    lines += [f"| {name} | {a:,} | {b:,} |" if isinstance(a, int) else f"| {name} | {a} | {b} |"
              for name, a, b in rows_out]
    lines += ["", f"migrate_legacy's own proof: {report.mismatches} user(s) whose preferences would change."]
    return "\n".join(lines)


def _probe(args: list[str]) -> dict:
    out = subprocess.run([sys.executable, "-m", "modernize.probe", "--oracle", str(ORACLE)] + args,
                         cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        if "NotImplementedError" in out.stderr:  # a TODO in starter/: say so, rather than a generic failure
            raise NotImplementedError(out.stderr.strip().splitlines()[-1])
        raise RuntimeError(out.stdout + out.stderr)
    return json.loads(out.stdout)


def report_characterize(data: Path = DATA) -> str:
    accepted = accepted_classes(data)
    agent = _probe(["--agent"])
    relay = _probe(["--src", str(ORACLE / "src")] + [x for a in accepted for x in ("--accept", a)])
    tags = sorted(set(agent["by_tag"]) | set(relay["by_tag"]))
    lines = ["# Characterization against the legacy module", "",
             f"Cases: {agent['cases']:,}, from tests/notify/corpus.py (seed 9)", "",
             "| Measure | Agent's rewrite (#2291) | Relay 4.22.0 |", "| --- | ---: | ---: |",
             f"| Decisions that differ from the legacy module | {agent['decision_differences']:,} | "
             f"{relay['decision_differences']:,} |"]
    lines += [f"| ... in cases tagged {t} | {agent['by_tag'].get(t, 0):,} | {relay['by_tag'].get(t, 0):,} |"
              for t in tags]
    for cls in sorted(set(agent["prefs"]) | set(relay["prefs"])):
        lines.append(f"| Users whose get_prefs differs: {cls} | {agent['prefs'].get(cls, 0)} | "
                     f"{relay['prefs'].get(cls, 0)} |")
    def writes(r):
        return "no write functions" if r["write_sequences"] is None else f"{r['write_differences']} of {r['write_sequences']}"

    lines.append(f"| Write sequences after which reads or decisions differ | {writes(agent)} | {writes(relay)} |")
    lines.append(f"| Differences not accepted by a reviewer | {agent['decision_differences'] + agent['unaccepted_prefs']:,}"
                 f" | {relay['decision_differences'] + relay['unaccepted_prefs']:,} |")
    lines += ["", "Accepted: " + "; ".join(accepted) + " (data/accepted-differences.json)"]
    return "\n".join(lines)


def report_parallel(data: Path = DATA) -> str:
    tasks = parallel.load_tasks(data)
    base = {"src/relay/__init__.py": (ORACLE / "src" / "relay" / "__init__.py").read_text(encoding="utf-8")}
    steps, final = parallel.integrate(data, ORACLE, base, accepted_classes(data))
    rollback = {t["id"]: t["rollback"] for t in tasks}
    expected = {p.relative_to(ORACLE).as_posix(): p.read_text(encoding="utf-8")
                for p in sorted(ORACLE.rglob("*.py")) if "__pycache__" not in p.parts}
    lines = ["# Five worktrees, integrated in order (the agents are simulated)", "",
             "Waves: " + " then ".join("{" + ", ".join(w) + "}" for w in parallel.waves(tasks)),
             "Integration order: " + ", ".join(parallel.integration_order(tasks)),
             "Predicted overlaps: " + ("; ".join(f"{a} and {b} both touch {p}" for a, b, p in parallel.overlaps(tasks))
                                       or "none"), "",
             "| Step | PR | Files | Outside tests/ | In all | Three-way merges | Conflicts | Re-run | "
             "Decisions that differ | get_prefs differences (accepted) | Write sequences that differ | "
             "Shadow differences | Tests passed | Rollback |",
             "| --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for s in steps:
        p = s.probe
        prefs = sum(p["prefs"].values())
        lines.append(f"| {s.task} | {s.pr} | {s.files} | {s.lines_outside_tests} | {s.lines_in_all} | "
                     f"{', '.join(s.merged_three_way) or '-'} | {'; '.join(s.conflicts) or '-'} | "
                     f"{'yes' if s.rerun else 'no'} | {p['decision_differences']} | {prefs} "
                     f"({prefs - p['unaccepted_prefs']}) | {p['write_differences']} of {p['write_sequences']} | "
                     f"{p['shadow_differences']} | {s.tests_passed} | {rollback[s.task]} |")
    big = max(steps, key=lambda s: s.lines_in_all)
    most_code = max(steps, key=lambda s: s.lines_outside_tests)
    lines += ["", f"Characterization cases at every step: {steps[0].probe['cases']:,}; write sequences: "
                  f"{steps[0].probe['write_sequences']}",
              f"Largest step in all: {big.task}, {big.lines_in_all} changed lines ({big.lines_outside_tests} outside "
              f"tests/); most outside tests/: {most_code.task}, {most_code.lines_outside_tests}",
              f"Integrated result equals Relay 4.22.0's notify package and tests: {'yes' if final == expected else 'no'}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modernize.report")
    ap.add_argument("report", choices=["incident", "characterize", "parallel"])
    args = ap.parse_args(argv)
    out = {"incident": report_incident, "characterize": report_characterize, "parallel": report_parallel}[args.report]()
    sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
