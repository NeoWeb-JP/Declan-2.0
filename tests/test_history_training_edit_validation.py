"""Training edits reject invalid source phrases without changing stored corrections."""

import unittest

import history


class TrainingEditValidationTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.directory = tempfile.TemporaryDirectory()
        self.old_database = history.DATABASE
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def tearDown(self):
        history.DATABASE = self.old_database
        self.directory.cleanup()

    def test_edit_rejects_oversized_or_control_character_phrase(self):
        history.teach_phrase("lights on", "turn on lights")
        for phrase in ("x" * 121, "lights\non", "   "):
            with self.subTest(phrase=repr(phrase)):
                with self.assertRaisesRegex(ValueError, "valid phrase"):
                    history.edit_intent(phrase, "turn off lights", "turn on lights")
        self.assertEqual(history.learned_intent("lights on"), "turn on lights")

    def test_valid_edit_preserves_stale_tab_protection(self):
        history.teach_phrase("lights on", "turn on lights")
        history.edit_intent("lights on", "switch on lights", "turn on lights")
        self.assertEqual(history.learned_intent("lights on"), "switch on lights")
        with self.assertRaisesRegex(ValueError, "another tab"):
            history.edit_intent("lights on", "turn off lights", "turn on lights")


if __name__ == "__main__":
    unittest.main()
