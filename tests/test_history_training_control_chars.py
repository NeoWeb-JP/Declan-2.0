"""Reject control characters before training normalisation can hide them."""

import tempfile
import unittest
from pathlib import Path

from declan.core import history


class TrainingControlCharacterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.old_database = history.DATABASE
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def tearDown(self):
        history.DATABASE = self.old_database
        self.directory.cleanup()

    def test_manual_training_rejects_control_characters(self):
        for phrase, target in (
            ("lights\non", "turn on lights"),
            ("lights on", "turn\ton lights"),
            ("lights\ron", "turn on lights"),
        ):
            with self.subTest(phrase=phrase, target=target):
                with self.assertRaises(ValueError):
                    history.teach_phrase(phrase, target)
        self.assertEqual(history.learned_intents(), {})

    def test_automatic_retry_cannot_insert_control_characters(self):
        with self.assertRaises(ValueError):
            history.teach_phrase("lights\non", "turn on lights", automatic=True)
        self.assertEqual(history.learned_intents(), {})

    def test_teach_from_history_rejects_bad_target_but_accepts_normal(self):
        turn_id = history.record("session", "assist", "lights on", "sorry")
        with self.assertRaises(ValueError):
            history.teach_intent(turn_id, "turn\non lights", "sorry")
        self.assertEqual(history.learned_intents(), {})
        history.teach_intent(turn_id, "turn on lights", "sorry")
        self.assertEqual(history.learned_intent("lights on"), "turn on lights")


if __name__ == "__main__":
    unittest.main()
