"""Future-dated History rows must not leak into retained reads or training."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from declan.core import history


class FutureHistoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", old_database)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_future_turn_is_not_in_history_or_training(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            valid_id = history.record("s", "assist", "lights on", "ok")
            with history.database() as connection:
                cursor = connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (now + 3600, "s", "assist", "future lights", "ok"),
                )
                future_id = cursor.lastrowid
            self.assertEqual([row["id"] for row in history.recent()], [valid_id])
            with self.assertRaises(ValueError):
                history.teach_intent(future_id, "turn on lights", "sorry")
            self.assertEqual(history.learned_intents(), {})
            history.teach_intent(valid_id, "turn on lights", "sorry")
            self.assertEqual(history.learned_intent("lights on"), "turn on lights")

    def test_future_recording_is_not_eligible_for_review(self):
        now = 2_000_000.0
        with patch.object(history, "time", return_value=now):
            with history.database() as connection:
                for timestamp, interaction in (
                    (now, "valid_recording"),
                    (now + 3600, "future_recording"),
                ):
                    connection.execute(
                        "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (timestamp, "s", "assist", "hello", "ok",
                         json.dumps({"interaction_id": interaction})),
                    )
            self.assertEqual(
                history.verified_recording_turns(["valid_recording", "future_recording"]),
                {"valid_recording": 1},
            )


if __name__ == "__main__":
    unittest.main()
