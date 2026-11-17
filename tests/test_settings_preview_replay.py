"""Guard against replaying a settings import preview after it has been applied."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsPreviewReplayTests(unittest.TestCase):
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
    def document(value):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {"DECLAN_MOVIE_SCRIPT": value}}

    def test_applied_preview_cannot_be_replayed(self):
        document = self.document("script.first")
        token = configuration.preview(document)["expected"]
        configuration.apply(document, token)
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(document, token)
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.first")

    def test_rejected_replay_does_not_overwrite_recovery(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.original"))
        first = self.document("script.first")
        first_token = configuration.preview(first)["expected"]
        configuration.apply(first, first_token)
        second = self.document("script.second")
        configuration.apply(second, configuration.preview(second)["expected"])
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(first, first_token)
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.second")
        self.assertEqual(configuration.recovery()["settings"]["DECLAN_MOVIE_SCRIPT"],
                         "script.first")

    def test_fresh_preview_allows_subsequent_import(self):
        first = self.document("script.first")
        configuration.apply(first, configuration.preview(first)["expected"])
        second = self.document("script.second")
        configuration.apply(second, configuration.preview(second)["expected"])
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.second")


if __name__ == "__main__":
    unittest.main()
