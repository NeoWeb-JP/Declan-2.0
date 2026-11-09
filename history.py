"""Local retention and export for Declan chat turns."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import time


DATABASE = Path(__file__).resolve().parent / ".data" / "conversations.sqlite3"
RETENTION_SECONDS = 30 * 24 * 60 * 60


@contextmanager
def database():
    DATABASE.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=2)
    try:
        with connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                session_id TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                reply TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS turns_created ON turns(created_at)")
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(turns)")}
            if "outcome" not in columns:
                connection.execute("ALTER TABLE turns ADD COLUMN outcome TEXT")
            if "routine_status" not in columns:
                connection.execute("ALTER TABLE turns ADD COLUMN routine_status TEXT")
            connection.execute("DELETE FROM turns WHERE created_at < ?", (time() - RETENTION_SECONDS,))
            yield connection
    finally:
        connection.close()


def prune():
    with database():
        pass


def has_recent_assist():
    with database() as connection:
        return connection.execute(
            "SELECT 1 FROM turns WHERE source = ? AND created_at >= ? LIMIT 1",
            ("assist", time() - 300),
        ).fetchone() is not None


def record(session_id, source, message, reply, outcome=None, routine_status=None):
    with database() as connection:
        connection.execute(
            "INSERT INTO turns(created_at, session_id, source, message, reply, outcome, routine_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (time(), session_id, source, message, reply, outcome, routine_status),
        )


def recent(before=None, limit=50):
    with database() as connection:
        connection.row_factory = sqlite3.Row
        query = "SELECT * FROM turns"
        args = []
        if before is not None:
            query += " WHERE id < ?"
            args.append(before)
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            args.append(limit)
        turns = [dict(row) for row in connection.execute(query, args)]
    for turn in turns:
        turn["created_at"] = datetime.fromtimestamp(turn["created_at"], timezone.utc).isoformat()
    return turns
