"""Local retention and export for Declan chat turns."""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import time
from threading import Lock


DATABASE = Path(__file__).resolve().parent / ".data" / "conversations.sqlite3"
SPEAKER_THRESHOLD = 0.75
_SCHEMA_LOCK = Lock()
_initialized = set()


def retention_seconds():
    value = os.environ.get('DECLAN_HISTORY_RETENTION_DAYS', '30')
    if not re.fullmatch(r'(?:[1-9]|[12][0-9]|30)', value):
        raise ValueError('DECLAN_HISTORY_RETENTION_DAYS must be a whole number from 1 to 30.')
    return int(value) * 24 * 60 * 60


def speaker_match(value):
    """Keep display metadata only, and label uncertain identities Unknown."""
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    confidence = value.get("confidence")
    interaction_id = value.get("interaction_id")
    match = {"name": "Unknown"}
    if isinstance(interaction_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", interaction_id):
        match["interaction_id"] = interaction_id
    if type(confidence) in (int, float) and 0 <= confidence <= 1:
        match["confidence"] = confidence
        if isinstance(name, str) and re.fullmatch(r"[^\W\d_][\w '\u2019-]{0,39}", name):
            if name.casefold() not in {"unknown", "unidentified", "none"}:
                display_name = "Edd" if name.casefold() == "ed" else name
                if confidence >= SPEAKER_THRESHOLD:
                    match["name"] = display_name
                else:
                    match["candidate"] = display_name
    return match


def initialize():
    """Migrate once per database file, before starting HTTP workers."""
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with _SCHEMA_LOCK:
        identity = (DATABASE.resolve(), DATABASE.stat().st_ino) if DATABASE.exists() else None
        if identity in _initialized:
            return
        connection = sqlite3.connect(DATABASE, timeout=2)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("""CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL, session_id TEXT NOT NULL,
                    source TEXT NOT NULL, message TEXT NOT NULL, reply TEXT NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS turns_created ON turns(created_at)")
                columns = {row[1] for row in connection.execute("PRAGMA table_info(turns)")}
                for column in ("outcome", "routine_status", "action_results", "phrase_suggestion",
                               "speaker_match", "diagnostic_id"):
                    if column not in columns:
                        connection.execute(f"ALTER TABLE turns ADD COLUMN {column} TEXT")
                connection.execute("CREATE TABLE IF NOT EXISTS learned_intents "
                                   "(phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
            _initialized.add((DATABASE.resolve(), DATABASE.stat().st_ino))
        finally:
            connection.close()


@contextmanager
def database():
    initialize()  # Also supports library callers and isolated test databases.
    connection = sqlite3.connect(DATABASE, timeout=2)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def prune():
    with database() as connection:
        connection.execute("DELETE FROM turns WHERE created_at < ?", (time() - retention_seconds(),))


def _intent_table(connection):
    """Compatibility hook; the table is now created by initialize()."""


def normalize_phrase(text):
    return " ".join(text.casefold().strip(" .?!").split())


def learned_intents():
    with database() as connection:
        _intent_table(connection)
        return dict(connection.execute("SELECT phrase, target FROM learned_intents ORDER BY phrase"))


def learned_intent(phrase):
    with database() as connection:
        _intent_table(connection)
        row = connection.execute("SELECT target FROM learned_intents WHERE phrase = ?", (phrase,)).fetchone()
        return row[0] if row else None


def teach_intent(turn_id, target, unmatched_reply):
    with database() as connection:
        turn = connection.execute(
            "SELECT message FROM turns WHERE id = ? AND source IN ('assist', 'browser_voice') "
            "AND outcome IS NULL AND reply = ?", (turn_id, unmatched_reply),
        ).fetchone()
        phrase = normalize_phrase(turn[0]) if turn else ""
        if not 0 < len(phrase) <= 120:
            raise ValueError("Choose a missed voice command from history (up to 120 characters).")
        target = normalize_phrase(target)
        if not 0 < len(target) <= 120 or any(ord(char) < 32 for char in target):
            raise ValueError("Enter the command you meant, up to 120 characters.")
        if target == phrase:
            raise ValueError("Enter a different command from the missed transcript.")
        _intent_table(connection)
        connection.execute(
            "INSERT INTO learned_intents(phrase, target) VALUES (?, ?) "
            "ON CONFLICT(phrase) DO UPDATE SET target = excluded.target", (phrase, target),
        )


def forget_intent(phrase):
    with database() as connection:
        _intent_table(connection)
        connection.execute("DELETE FROM learned_intents WHERE phrase = ?", (phrase,))


def clear():
    """Remove all saved conversation turns in one transaction."""
    with database() as connection:
        return connection.execute("DELETE FROM turns").rowcount


def has_recent_assist():
    with database() as connection:
        return connection.execute(
            "SELECT 1 FROM turns WHERE source = ? AND created_at >= ? LIMIT 1",
            ("assist", time() - 300),
        ).fetchone() is not None


def record(session_id, source, message, reply, outcome=None, routine_status=None, action_results=None,
           phrase_suggestion=None, *, speaker=None, diagnostic_id=None):
    match = speaker_match(speaker) if source == "assist" else None
    with database() as connection:
        connection.execute(
            "INSERT INTO turns(created_at, session_id, source, message, reply, outcome, routine_status, "
            "action_results, phrase_suggestion, speaker_match, diagnostic_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time(), session_id, source, message, reply, outcome, routine_status,
             json.dumps(action_results) if action_results else None, phrase_suggestion,
             json.dumps(match) if match else None, diagnostic_id),
        )


def recent(before=None, limit=50):
    with database() as connection:
        connection.row_factory = sqlite3.Row
        query = "SELECT * FROM turns WHERE created_at >= ?"
        args = [time() - retention_seconds()]
        if before is not None:
            query += " AND id < ?"
            args.append(before)
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            args.append(limit)
        turns = [dict(row) for row in connection.execute(query, args)]
    for turn in turns:
        turn["created_at"] = datetime.fromtimestamp(turn["created_at"], timezone.utc).isoformat()
        turn["action_results"] = json.loads(turn["action_results"]) if turn["action_results"] else []
        turn["speaker_match"] = json.loads(turn["speaker_match"]) if turn["speaker_match"] else None
    return turns


def edit_intent(phrase, target, previous):
    """Edit an existing correction; a stale tab must not overwrite a newer edit."""
    if not all(isinstance(value, str) for value in (phrase, target, previous)):
        raise ValueError("Enter a valid phrase and command.")
    phrase = normalize_phrase(phrase)
    target = normalize_phrase(target)
    if not 0 < len(target) <= 120 or any(ord(char) < 32 for char in target) or target == phrase:
        raise ValueError("Enter a different command, up to 120 characters.")
    with database() as connection:
        _intent_table(connection)
        changed = connection.execute(
            "UPDATE learned_intents SET target = ? WHERE phrase = ? AND target = ?", (target, phrase, previous))
        if changed.rowcount != 1:
            raise ValueError("This intention changed in another tab. Refresh before editing.")

