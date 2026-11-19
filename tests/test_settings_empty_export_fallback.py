"""Ensure exported and recovery settings respect effective fallback values."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsEmptyFallbackTests(unittest.TestCase):
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

    def test_export_uses_environment_when_saved_value_is_empty(self):
        key = "DECLAN_MOVIE_SCRIPT"
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, ""))
        with patch.dict(os.environ, {key: "script.from_environment"}):
            self.assertEqual(configuration.get(key), "script.from_environment")
            self.assertEqual(configuration.export()["settings"][key], "script.from_environment")

    def test_export_keeps_nonempty_saved_value(self):
        key = "DECLAN_MOVIE_SCRIPT"
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, "script.saved"))
        with patch.dict(os.environ, {key: "script.from_environment"}):
            self.assertEqual(configuration.export()["settings"][key], "script.saved")

    def test_recovery_snapshot_uses_environment_fallback(self):
        key = "DECLAN_MOVIE_SCRIPT"
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, ""))
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {key: "script.new"}}
        with patch.dict(os.environ, {key: "script.from_environment"}):
            configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(configuration.recovery()["settings"][key], "script.from_environment")


if __name__ == "__main__":
    unittest.main()
