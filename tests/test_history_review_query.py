"""History lookup index and recording-review fast path regression tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.core import history


class HistoryReviewQueryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        original = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", original)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_source_time_index_created_for_new_database(self):
        with history.database() as connection:
            indexes = {row[1] for row in connection.execute("PRAGMA index_list(turns)")}
        self.assertIn("turns_source_created", indexes)

    def test_empty_recording_request_avoids_database_scan(self):
        with patch.object(history, "database", side_effect=AssertionError("unexpected query")):
            self.assertEqual(history.verified_recording_turns([]), {})

    def test_recording_review_keeps_valid_and_ambiguous_behavior(self):
        with history.database() as connection:
            for name in ("good", "duplicate", "duplicate"):
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (history.time(), "session", "assist", "hello", "hi",
                     json.dumps({"interaction_id": name})),
                )
        self.assertEqual(history.verified_recording_turns(["good", "duplicate"]), {"good": 1})


if __name__ == "__main__":
    unittest.main()
