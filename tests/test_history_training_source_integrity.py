"""Training sources must be actual assist turns and clean raw phrases."""

import tempfile
import unittest
from pathlib import Path

import history


class TrainingSourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.original_database = history.DATABASE
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def tearDown(self):
        history.DATABASE = self.original_database
        self.directory.cleanup()

    def test_training_allows_non_assist_history_turn(self):
        turn_id = history.record("session", "browser_keyboard", "turn lights on", "sorry")
        history.teach_intent(turn_id, "switch lights on", "sorry")
        self.assertEqual(history.learned_intent("turn lights on"), "switch lights on")

    def test_training_rejects_invalid_recorded_source(self):
        turn_id = history.record("session", "assist", "turn\nlights on", "sorry")
        with self.assertRaisesRegex(ValueError, "Choose a command from history"):
            history.teach_intent(turn_id, "switch lights on", "sorry")
        self.assertEqual(history.learned_intents(), {})

    def test_training_allows_clean_assist_source(self):
        turn_id = history.record("session", "assist", "turn lights on", "sorry")
        history.teach_intent(turn_id, "switch lights on", "sorry")
        self.assertEqual(history.learned_intent("turn lights on"), "switch lights on")

    def test_edit_rejects_control_characters_in_target(self):
        history.teach_phrase("lights on", "turn on lights")
        for target in ("turn\non lights", "turn\ton lights", "turn\ron lights"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    history.edit_intent("lights on", target, "turn on lights")
        self.assertEqual(history.learned_intent("lights on"), "turn on lights")


if __name__ == "__main__":
    unittest.main()
