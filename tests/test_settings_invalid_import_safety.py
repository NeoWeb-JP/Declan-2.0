"""Ensure rejected settings imports never alter persisted state or recovery."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsInvalidImportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.existing"))
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("existing phrase", "existing target"))

        @contextmanager
        def database():
            yield self.db

        self.database_patch = patch.object(configuration.history, "database", database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.db.close)

    @staticmethod
    def document(settings=None, learned_intents=None):
        result = {"format": "declan-settings", "schema_version": 1,
                  "settings": settings if settings is not None else
                  {"DECLAN_MOVIE_SCRIPT": "script.new"}}
        if learned_intents is not None:
            result["learned_intents"] = learned_intents
        return result

    def assert_unchanged(self):
        self.assertEqual(dict(self.db.execute("SELECT key, value FROM server_settings")),
                         {"DECLAN_MOVIE_SCRIPT": "script.existing"})
        self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                         {"existing phrase": "existing target"})
        self.assertIsNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings_recovery'"
        ).fetchone())

    def test_invalid_entity_rejected_before_any_writes(self):
        document = self.document(settings={"DECLAN_MOVIE_SCRIPT": "remote.wrong"})
        with self.assertRaises(ValueError):
            configuration.apply(document, "irrelevant")
        self.assert_unchanged()

    def test_invalid_learning_rejected_before_any_writes(self):
        document = self.document(learned_intents={"same phrase": "same phrase"})
        with self.assertRaises(ValueError):
            configuration.apply(document, "irrelevant")
        self.assert_unchanged()

    def test_stale_preview_rejected_without_recovery_snapshot(self):
        document = self.document()
        token = configuration.preview(document)["expected"]
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_GOOD_NIGHT_SCRIPT", "script.changed"))
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(document, token)
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.existing")
        self.assertIsNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings_recovery'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
