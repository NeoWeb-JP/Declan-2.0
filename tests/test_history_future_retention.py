"""Retention must not leave invisible future-dated or malformed turns indefinitely."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import history


class HistoryFutureRetentionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", old_database)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_prune_removes_future_expired_and_malformed_timestamps(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            history.record("s", "assist", "current", "ok")
            with history.database() as connection:
                for timestamp, message in (
                    (now + 3600, "future"),
                    (now - 40 * 86400, "expired"),
                    ("bad", "malformed"),
                ):
                    connection.execute(
                        "INSERT INTO turns(created_at, session_id, source, message, reply) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (timestamp, "s", "assist", message, "ok"),
                    )
            history.prune()
            with history.database() as connection:
                remaining = [row[0] for row in connection.execute(
                    "SELECT message FROM turns ORDER BY id"
                )]
        self.assertEqual(remaining, ["current"])

    def test_prune_respects_configured_retention_boundary(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            with patch.dict("os.environ", {"DECLAN_HISTORY_RETENTION_DAYS": "1"}):
                with history.database() as connection:
                    for age, message in ((3600, "recent"), (2 * 86400, "old")):
                        connection.execute(
                            "INSERT INTO turns(created_at, session_id, source, message, reply) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (now - age, "s", "assist", message, "ok"),
                        )
                history.prune()
                with history.database() as connection:
                    remaining = [row[0] for row in connection.execute(
                        "SELECT message FROM turns"
                    )]
        self.assertEqual(remaining, ["recent"])


if __name__ == "__main__":
    unittest.main()
