"""Verify persisted settings precedence over environment and default values."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")

        @contextmanager
        def database():
            yield self.db

        self.database_patch = patch.object(configuration.history, "database", database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.db.close)

    def test_saved_nonempty_value_overrides_environment(self):
        key = "DECLAN_MOVIE_SCRIPT"
        with patch.dict(os.environ, {key: "script.environment"}):
            self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, "script.saved"))
            self.assertEqual(configuration.get(key, "script.fallback"), "script.saved")

    def test_empty_saved_value_uses_environment(self):
        key = "DECLAN_WEB_ASSIST_PIPELINE"
        with patch.dict(os.environ, {key: "environment-pipeline"}):
            self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, ""))
            self.assertEqual(configuration.get(key, "fallback-pipeline"), "environment-pipeline")

    def test_missing_saved_and_environment_value_uses_default(self):
        key = "DECLAN_GOOD_NIGHT_SCRIPT"
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configuration.get(key, "script.default"), "script.default")

    def test_unlisted_key_reads_environment_without_database(self):
        with patch.dict(os.environ, {"DECLAN_UNLISTED_TEST": "from-env"}):
            with patch.object(configuration.history, "database", side_effect=AssertionError("unexpected database access")):
                self.assertEqual(configuration.get("DECLAN_UNLISTED_TEST", "fallback"), "from-env")


if __name__ == "__main__":
    unittest.main()
