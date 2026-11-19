"""Training lookup and automatic correction mode contracts."""

import tempfile
import unittest
from pathlib import Path

from declan.core import history


class TrainingLookupContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        original = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", original)
        history.DATABASE = Path(directory.name) / "history.sqlite3"

    def test_lookup_uses_same_normalization_as_saved_training(self):
        history.teach_phrase("turn lights on", "switch lights on")
        self.assertEqual(history.learned_intent("  TURN LIGHTS ON?!  "), "switch lights on")
        self.assertEqual(history.learned_intent("turn lights on"), "switch lights on")

    def test_invalid_lookup_is_not_a_database_error(self):
        for phrase in (None, True, 123, "", "  ", "bad\nphrase", "x" * 121):
            with self.subTest(phrase=phrase):
                self.assertIsNone(history.learned_intent(phrase))

    def test_automatic_retry_never_overwrites_explicit_correction(self):
        history.teach_phrase("lights on", "switch lights on")
        history.teach_phrase("lights on", "turn on the lights", automatic=True)
        self.assertEqual(history.learned_intent("lights on"), "switch lights on")

    def test_invalid_automatic_mode_is_rejected_without_changes(self):
        for mode in ("false", "true", 0, 1, None):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ValueError, "Automatic training"):
                    history.teach_phrase("lights on", "switch lights on", automatic=mode)
        self.assertEqual(history.learned_intents(), {})

    def test_manual_correction_can_replace_automatic_retry(self):
        history.teach_phrase("lights on", "turn on lights", automatic=True)
        history.teach_phrase("lights on", "switch lights on", automatic=False)
        self.assertEqual(history.learned_intent("lights on"), "switch lights on")


if __name__ == "__main__":
    unittest.main()
