"""Fail-closed persistent monthly OpenAI spend reservation.

All amounts are integer micro-USD to avoid floating-point overspend. This
reserves a maximum cost *before* network access. A crashed request retains its
reservation until the month rolls over, favouring safety over availability.
"""
import sqlite3
from datetime import datetime, timezone

MICRO_USD = 1_000_000


def _month(now):
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("UTC-aware datetime required")
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def reserve(db, *, limit_micro_usd, max_request_micro_usd, now=None):
    """Reserve the full per-request ceiling atomically; return reservation ID.

    db is a caller-owned sqlite3.Connection with a writable persistent file.
    Do not use an in-memory database in production.
    """
    if (type(limit_micro_usd) is not int or type(max_request_micro_usd) is not int
            or limit_micro_usd < 0 or max_request_micro_usd <= 0
            or max_request_micro_usd > limit_micro_usd):
        raise ValueError("Invalid spend limits")
    month = _month(now)
    with db:
        db.execute("CREATE TABLE IF NOT EXISTS ai_budget (month TEXT PRIMARY KEY, reserved INTEGER NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS ai_reservation (id INTEGER PRIMARY KEY, month TEXT NOT NULL, ceiling INTEGER NOT NULL)")
        db.execute("INSERT OR IGNORE INTO ai_budget VALUES (?, 0)", (month,))
        cursor = db.execute(
            "UPDATE ai_budget SET reserved = reserved + ? "
            "WHERE month = ? AND reserved <= ? - ?",
            (max_request_micro_usd, month, limit_micro_usd, max_request_micro_usd),
        )
        if cursor.rowcount != 1:
            raise ValueError("Monthly OpenAI budget exhausted")
        cursor = db.execute("INSERT INTO ai_reservation(month, ceiling) VALUES (?, ?)", (month, max_request_micro_usd))
        return cursor.lastrowid


def settle(db, reservation_id, actual_micro_usd):
    """Release unused reservation; never accept a charge above its ceiling."""
    if type(reservation_id) is not int or type(actual_micro_usd) is not int or actual_micro_usd < 0:
        raise ValueError("Invalid settlement")
    with db:
        row = db.execute("SELECT month, ceiling FROM ai_reservation WHERE id = ?", (reservation_id,)).fetchone()
        if row is None or actual_micro_usd > row[1]:
            raise ValueError("Unknown reservation or exceeded ceiling")
        db.execute("UPDATE ai_budget SET reserved = reserved - ? WHERE month = ?",
                   (row[1] - actual_micro_usd, row[0]))
        db.execute("DELETE FROM ai_reservation WHERE id = ?", (reservation_id,))


def monthly_reserved(db, *, now=None):
    """Return zero until the first AI reservation creates the budget table."""
    month = _month(now)
    # Fresh installations have no ai_budget table until their first request.
    # A read-only settings page must not fail just because AI has never run.
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'ai_budget'"
    ).fetchone()
    if row is None:
        return 0
    row = db.execute("SELECT reserved FROM ai_budget WHERE month = ?", (month,)).fetchone()
    return row[0] if row else 0
