"""Local retention and export for Declan chat turns."""
import json
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import time
from database_schema_state import DatabaseSchemaState
from action_evidence_wire import action_evidence_to_wire


DATABASE = Path(__file__).resolve().parent / ".data" / "conversations.sqlite3"
SPEAKER_THRESHOLD = 0.75
SCHEMA_STATE = DatabaseSchemaState()


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
    match: dict[str, str | int | float] = {"name": "Unknown"}
    if isinstance(interaction_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", interaction_id):
        match["interaction_id"] = interaction_id
    if isinstance(confidence, (int, float)) and type(confidence) in (int, float) and math.isfinite(confidence) and 0 <= confidence <= 1:
        match["confidence"] = confidence
        if isinstance(name, str) and re.fullmatch(r"[^\W\d_][\w '\u2019-]{0,39}", name):
            if name.casefold() not in {"unknown", "unidentified", "none"}:
                display_name = name
                if confidence >= SPEAKER_THRESHOLD:
                    match["name"] = display_name
                else:
                    match["candidate"] = display_name
    return match


def initialize():
    """Migrate once per database file, before starting HTTP workers."""
    SCHEMA_STATE.ensure(DATABASE, _migrate_schema)


def _migrate_schema():
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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS turns_source_created ON turns(source, created_at)")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(turns)")}
            for column in ("outcome", "routine_status", "action_results", "phrase_suggestion",
                           "speaker_match", "diagnostic_id"):
                if column not in columns:
                    connection.execute(f"ALTER TABLE turns ADD COLUMN {column} TEXT")
            connection.execute("CREATE TABLE IF NOT EXISTS learned_intents "
                               "(phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
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
    """Discard expired, malformed and future-dated turns in the hourly cleanup."""
    now = time()
    with database() as connection:
        connection.execute(
            "DELETE FROM turns WHERE typeof(created_at) NOT IN ('integer', 'real') "
            "OR created_at < ? OR created_at > ?",
            (now - retention_seconds(), now),
        )


def _intent_table(connection):
    """Compatibility hook; the table is now created by initialize()."""


def normalize_phrase(text):
    return " ".join(text.casefold().strip(" .?!").split())


def validated_training_phrase(value, error):
    """Validate raw training input before normalisation can hide control chars."""
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise ValueError(error)
    normalized = normalize_phrase(value)
    if not 0 < len(normalized) <= 120:
        raise ValueError(error)
    return normalized


def learned_intents():
    with database() as connection:
        _intent_table(connection)
        return dict(connection.execute("SELECT phrase, target FROM learned_intents ORDER BY phrase"))


def learned_intent(phrase):
    """Resolve corrections using the same normalisation as training writes."""
    if not isinstance(phrase, str):
        return None
    try:
        phrase = validated_training_phrase(phrase, "Invalid trained phrase.")
    except ValueError:
        return None
    with database() as connection:
        _intent_table(connection)
        row = connection.execute("SELECT target FROM learned_intents WHERE phrase = ?", (phrase,)).fetchone()
        return row[0] if row else None


def teach_intent(turn_id, target, unmatched_reply):
    if type(turn_id) is not int or turn_id <= 0:
        raise ValueError("Choose a valid command from history.")
    now = time()
    with database() as connection:
        turn = connection.execute(
            "SELECT message FROM turns WHERE id = ? AND created_at BETWEEN ? AND ?",
            (turn_id, now - retention_seconds(), now),
        ).fetchone()
        phrase = validated_training_phrase(
            turn[0] if turn else "", "Choose a command from history (up to 120 characters).")
        target = validated_training_phrase(target, "Enter the command you meant, up to 120 characters.")
        if target == phrase:
            raise ValueError("Enter a different command from the missed transcript.")
        _intent_table(connection)
        connection.execute(
            "INSERT INTO learned_intents(phrase, target) VALUES (?, ?) "
            "ON CONFLICT(phrase) DO UPDATE SET target = excluded.target", (phrase, target),
        )


def forget_intent(phrase):
    phrase = validated_training_phrase(phrase, "Choose a valid trained phrase.")
    with database() as connection:
        _intent_table(connection)
        connection.execute("DELETE FROM learned_intents WHERE phrase = ?", (phrase,))


def teach_phrase(phrase, target, *, automatic=False):
    """Save an explicit correction, or add a retry without overwriting user training."""
    if type(automatic) is not bool:
        raise ValueError("Automatic training must be enabled or disabled.")
    if not isinstance(phrase, str) or not isinstance(target, str):
        raise ValueError("Enter a phrase and the command you meant.")
    phrase = validated_training_phrase(phrase, "Enter a different command, up to 120 characters.")
    target = validated_training_phrase(target, "Enter a different command, up to 120 characters.")
    if phrase == target:
        raise ValueError("Enter a different command, up to 120 characters.")
    with database() as connection:
        if automatic:
            connection.execute(
                "INSERT INTO learned_intents(phrase, target) VALUES (?, ?) "
                "ON CONFLICT(phrase) DO NOTHING", (phrase, target))
        else:
            connection.execute(
                "INSERT INTO learned_intents(phrase, target) VALUES (?, ?) "
                "ON CONFLICT(phrase) DO UPDATE SET target = excluded.target", (phrase, target))


def clear():
    """Remove all saved conversation turns in one transaction."""
    with database() as connection:
        return connection.execute("DELETE FROM turns").rowcount


def has_recent_assist():
    now = time()
    with database() as connection:
        return connection.execute(
            "SELECT 1 FROM turns WHERE source = ? AND created_at BETWEEN ? AND ? LIMIT 1",
            ("assist", now - min(300, retention_seconds()), now),
        ).fetchone() is not None


def record(session_id, source, message, reply, outcome=None, routine_status=None, action_results=None,
           phrase_suggestion=None, *, speaker=None, diagnostic_id=None):
    stored_actions = action_evidence_to_wire(action_results)
    match = speaker_match(speaker) if source == "assist" else None
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO turns(created_at, session_id, source, message, reply, outcome, routine_status, "
            "action_results, phrase_suggestion, speaker_match, diagnostic_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time(), session_id, source, message, reply, outcome, routine_status,
             json.dumps(stored_actions) if stored_actions else None, phrase_suggestion,
             json.dumps(match) if match else None, diagnostic_id),
        )
        return cursor.lastrowid


def recent(before=None, limit=50):
    """Read retained turns with bounded, well-formed pagination arguments."""
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 500):
        raise ValueError("History page size must be between 1 and 500.")
    if before is not None and (type(before) is not int or before <= 0):
        raise ValueError("History cursor must be a positive integer.")
    now = time()
    with database() as connection:
        connection.row_factory = sqlite3.Row
        query = (
            "SELECT * FROM turns WHERE typeof(created_at) IN ('integer', 'real') "
            "AND created_at BETWEEN ? AND ?"
        )
        args = [now - retention_seconds(), now]
        if before is not None:
            query += " AND id < ?"
            args.append(before)
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            args.append(limit)
        turns = [dict(row) for row in connection.execute(query, args)]
    valid_turns = []
    for turn in turns:
        try:
            timestamp = float(turn["created_at"])
            if not math.isfinite(timestamp):
                continue
            turn["created_at"] = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            # A corrupt legacy timestamp must not take down the entire History page.
            continue
        # Corrupt legacy JSON must not break the entire History page.
        for field, expected_type, fallback in (
            ("action_results", list, []),
            ("speaker_match", dict, None),
        ):
            try:
                decoded = json.loads(turn[field]) if turn[field] else fallback
            except (TypeError, ValueError):
                decoded = fallback
            turn[field] = decoded if type(decoded) is expected_type else fallback
        valid_turns.append(turn)
    return valid_turns


def verified_recording_turns(interaction_ids):
    """Only expose unique, explicitly linked voice turns from the review window."""
    if not isinstance(interaction_ids, list) or len(interaction_ids) > 100 or any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value)
        for value in interaction_ids
    ):
        raise ValueError("Invalid recording identifiers.")
    requested = set(interaction_ids)
    if not requested:
        return {}
    matches = {}
    ambiguous = set()
    now = time()
    with database() as connection:
        rows = connection.execute(
            "SELECT id, speaker_match FROM turns WHERE source = 'assist' AND "
            "created_at BETWEEN ? AND ? AND speaker_match IS NOT NULL",
            (now - min(7 * 24 * 60 * 60, retention_seconds()), now),
        )
        for turn_id, encoded in rows:
            try:
                speaker = json.loads(encoded)
            except (TypeError, ValueError):
                continue
            recording_id = speaker.get("interaction_id") if isinstance(speaker, dict) else None
            if type(recording_id) is not str or recording_id not in requested:
                continue
            if recording_id in matches:
                ambiguous.add(recording_id)
            else:
                matches[recording_id] = turn_id
    return {key: value for key, value in matches.items() if key not in ambiguous}



def edit_intent(phrase, target, previous):
    """Edit an existing correction; a stale tab must not overwrite a newer edit."""
    if not all(isinstance(value, str) for value in (phrase, target, previous)):
        raise ValueError("Enter a valid phrase and command.")
    phrase = validated_training_phrase(phrase, "Enter a valid phrase, up to 120 characters.")
    target = validated_training_phrase(target, "Enter a different command, up to 120 characters.")
    if target == phrase:
        raise ValueError("Enter a different command, up to 120 characters.")
    with database() as connection:
        _intent_table(connection)
        changed = connection.execute(
            "UPDATE learned_intents SET target = ? WHERE phrase = ? AND target = ?", (target, phrase, previous))
        if changed.rowcount != 1:
            raise ValueError("This intention changed in another tab. Refresh before editing.")

