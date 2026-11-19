"""History query and training entry-point integrity regression tests."""

import tempfile
import unittest
from pathlib import Path

import history


class HistoryEntryIntegrityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", old_database)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_training_rejects_invalid_history_ids(self):
        turn_id: object
        for turn_id in (True, False, 0, -1, "1", 1.5, [], {}):
            with self.subTest(turn_id=turn_id):
                with self.assertRaisesRegex(ValueError, "valid command"):
                    history.teach_intent(turn_id, "switch lights on", "sorry")

    def test_valid_history_training_still_works(self):
        turn_id = history.record("s", "assist", "lights on", "sorry")
        history.teach_intent(turn_id, "switch lights on", "sorry")
        self.assertEqual(history.learned_intent("lights on"), "switch lights on")

    def test_forget_validates_phrase_without_changing_other_training(self):
        history.teach_phrase("lights on", "switch lights on")
        for phrase in ("", "   ", "lights\non", "x" * 121, 123):
            with self.subTest(phrase=phrase):
                with self.assertRaises(ValueError):
                    history.forget_intent(phrase)
        self.assertEqual(history.learned_intent("lights on"), "switch lights on")
        history.forget_intent("  LIGHTS ON? ")
        self.assertIsNone(history.learned_intent("lights on"))

    def test_corrupt_timestamp_does_not_consume_page_slot(self):
        first = history.record("s", "assist", "first", "ok")
        second = history.record("s", "assist", "second", "ok")
        with history.database() as connection:
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply) "
                "VALUES (?, ?, ?, ?, ?)",
                ("invalid", "s", "assist", "bad", "ok"),
            )
        self.assertEqual([row["id"] for row in history.recent(limit=2)], [second, first])


if __name__ == "__main__":
    unittest.main()
