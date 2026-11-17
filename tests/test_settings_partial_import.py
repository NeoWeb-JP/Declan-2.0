"""Verify partial settings imports preserve unrelated persisted configuration."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsPartialImportTests(unittest.TestCase):
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

    def test_partial_import_preserves_unmentioned_settings(self):
        self.db.executemany("INSERT INTO server_settings VALUES (?, ?)", [
            ("DECLAN_MOVIE_SCRIPT", "script.old_movie"),
            ("DECLAN_GOOD_NIGHT_SCRIPT", "script.night"),
            ("DECLAN_WEB_ASSIST_PIPELINE", "pipeline-one"),
        ])
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": "script.new_movie"}}
        configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(dict(self.db.execute("SELECT key, value FROM server_settings")), {
            "DECLAN_MOVIE_SCRIPT": "script.new_movie",
            "DECLAN_GOOD_NIGHT_SCRIPT": "script.night",
            "DECLAN_WEB_ASSIST_PIPELINE": "pipeline-one",
        })

    def test_empty_imported_value_reverts_to_environment_default(self):
        key = "DECLAN_MOVIE_SCRIPT"
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, "script.saved"))
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {key: ""}}
        with patch.dict("os.environ", {key: "script.environment"}):
            configuration.apply(document, configuration.preview(document)["expected"])
            self.assertEqual(configuration.get(key), "script.environment")
        self.assertEqual(self.db.execute(
            "SELECT value FROM server_settings WHERE key = ?", (key,)).fetchone()[0], "")

    def test_empty_settings_document_leaves_existing_settings_untouched(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.saved"))
        document = {"format": "declan-settings", "schema_version": 1, "settings": {}}
        configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.saved")


if __name__ == "__main__":
    unittest.main()
