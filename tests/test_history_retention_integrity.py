"""History retention cleanup and recent-assist clock boundary regressions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.core import history


class HistoryRetentionIntegrityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        original = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", original)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_prune_removes_corrupt_and_expired_rows_but_keeps_recent(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            history.record("s", "assist", "recent", "ok")
            with history.database() as connection:
                for timestamp, message in (
                    ("broken-date", "corrupt"),
                    (now - 40 * 86400, "expired"),
                ):
                    connection.execute(
                        "INSERT INTO turns(created_at, session_id, source, message, reply) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (timestamp, "s", "assist", message, "ok"),
                    )
            history.prune()
            with history.database() as connection:
                messages = [row[0] for row in connection.execute("SELECT message FROM turns")]
        self.assertEqual(messages, ["recent"])

    def test_future_assist_turn_is_not_recent(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            with history.database() as connection:
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (now + 3600, "s", "assist", "future", "ok"),
                )
            self.assertFalse(history.has_recent_assist())
            history.record("s", "assist", "current", "ok")
            self.assertTrue(history.has_recent_assist())


if __name__ == "__main__":
    unittest.main()
