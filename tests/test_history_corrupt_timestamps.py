"""Corrupt legacy History timestamps cannot break the History page."""

import tempfile
import unittest
from pathlib import Path

from declan.core import history


class HistoryTimestampTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", old_database)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_invalid_legacy_timestamp_is_skipped(self):
        history.record("session", "assist", "good", "ok")
        with history.database() as connection:
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply) "
                "VALUES (?, ?, ?, ?, ?)",
                ("invalid-time", "old", "assist", "bad", "bad"),
            )
        rows = history.recent()
        self.assertEqual([row["message"] for row in rows], ["good"])

    def test_valid_history_timestamps_remain_iso_utc(self):
        history.record("session", "assist", "hello", "hi")
        rows = history.recent()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["created_at"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
