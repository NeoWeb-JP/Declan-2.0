"""Settings previews must not silently apply after environment defaults change."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsPreviewEnvironmentDriftTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")

        @contextmanager
        def database():
            with self.db:
                yield self.db

        self.database_patch = patch.object(configuration.history, "database", database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.db.close)

    def test_environment_change_invalidates_preview(self):
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": ""}}
        with patch.dict(os.environ, {"DECLAN_MOVIE_SCRIPT": "script.original"}):
            token = configuration.preview(document)["expected"]
        with patch.dict(os.environ, {"DECLAN_MOVIE_SCRIPT": "script.changed"}):
            with self.assertRaisesRegex(ValueError, "Preview the file again"):
                configuration.apply(document, token)
        self.assertEqual(list(self.db.execute("SELECT * FROM server_settings")), [])

    def test_unchanged_environment_accepts_preview(self):
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": "script.movie"}}
        with patch.dict(os.environ, {"DECLAN_MOVIE_SCRIPT": "script.default"}):
            token = configuration.preview(document)["expected"]
            configuration.apply(document, token)
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.movie")


if __name__ == "__main__":
    unittest.main()
