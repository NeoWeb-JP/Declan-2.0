"""Verify settings export excludes credentials and opts in to learned phrases."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsExportBoundaryTests(unittest.TestCase):
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

    def test_export_contains_only_allowlisted_settings(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.saved_movie"))
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_HA_TOKEN", "stored-secret"))
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("movie please", "movie time"))
        with patch.dict(os.environ, {"DECLAN_GOOD_NIGHT_SCRIPT": "script.from_env",
                                     "DECLAN_HA_TOKEN": "environment-secret"}):
            result = configuration.export()
        self.assertEqual(result["format"], "declan-settings")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["settings"]["DECLAN_MOVIE_SCRIPT"], "script.saved_movie")
        self.assertEqual(result["settings"]["DECLAN_GOOD_NIGHT_SCRIPT"], "script.from_env")
        self.assertEqual(set(result["settings"]), set(configuration.FIELDS))
        self.assertNotIn("DECLAN_HA_TOKEN", result["settings"])
        self.assertNotIn("learned_intents", result)

    def test_export_learning_is_explicit_opt_in(self):
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("movie please", "movie time"))
        result = configuration.export(include_learning=True)
        self.assertEqual(result["learned_intents"], {"movie please": "movie time"})
        self.assertEqual(set(result["settings"]), set(configuration.FIELDS))


if __name__ == "__main__":
    unittest.main()
