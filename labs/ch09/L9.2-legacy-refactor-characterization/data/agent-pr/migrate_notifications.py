# Reconstructed for the book's composite incident (Chapter 9): the migration in agent pull request #2291,
# merged on 2026-12-08 and run by the deploy train at 15:00 UTC. Input data for Lab 9.2; do not "fix" it here.
# Lab 9.1's data/incident-pr.json quotes four of these lines.
"""Migrate notification preferences to the new schema."""


def upgrade(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS notify_optouts (user_id INTEGER NOT NULL, type TEXT NOT NULL,
                                               PRIMARY KEY (user_id, type));
    CREATE TABLE IF NOT EXISTS notify_spam_marks (user_id INTEGER PRIMARY KEY, marked_on TEXT NOT NULL);
    """)
    rows = conn.execute("SELECT user_id, muted_types, spam_marked_on FROM notification_prefs "
                        "WHERE muted_types <> ''").fetchall()
    for user_id, muted, spam in rows:
        for t in muted.split(","):
            if t.strip():
                conn.execute("INSERT OR IGNORE INTO notify_optouts VALUES (?, ?)", (user_id, t.strip().lower()))
        if spam:
            conn.execute("INSERT INTO notify_spam_marks VALUES (?, ?)", (user_id, spam))
    conn.execute("DROP TABLE notification_prefs")
    conn.commit()
