"""Verify settings import preview fingerprints reject stale or altered imports."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsPreviewConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")

        @contextmanager
        def database():
            yield self.db

        self.database_patch = patch.object(configuration.history, "database", database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.db.close)

    @staticmethod
    def document(value="script.movie"):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {"DECLAN_MOVIE_SCRIPT": value}}

    def test_preview_exposes_import_details_without_writing_settings(self):
        document = self.document()
        result = configuration.preview(document)
        self.assertEqual(result["settings"], document["settings"])
        self.assertEqual(result["learning_count"], 0)
        self.assertFalse(result["replaces_learning"])
        self.assertTrue(result["expected"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM server_settings").fetchone()[0], 0)

    def test_preview_detects_optional_learning_replacement(self):
        document = self.document()
        document["learned_intents"] = {"play movie": "movie time"}
        result = configuration.preview(document)
        self.assertEqual(result["learning_count"], 1)
        self.assertTrue(result["replaces_learning"])

    def test_stale_preview_cannot_apply_after_settings_change(self):
        document = self.document()
        token = configuration.preview(document)["expected"]
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_GOOD_NIGHT_SCRIPT", "script.changed"))
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(document, token)
        self.assertEqual(self.db.execute(
            "SELECT value FROM server_settings WHERE key = 'DECLAN_MOVIE_SCRIPT'").fetchone(), None)

    def test_preview_token_is_bound_to_document_contents(self):
        original = self.document()
        token = configuration.preview(original)["expected"]
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(self.document("script.different"), token)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM server_settings").fetchone()[0], 0)

    def test_missing_preview_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(self.document(), None)


if __name__ == "__main__":
    unittest.main()
