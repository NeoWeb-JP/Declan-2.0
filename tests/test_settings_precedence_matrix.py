"""Verify saved/environment/default precedence for every allowlisted setting."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsPrecedenceMatrixTests(unittest.TestCase):
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
    def valid_value(domain, suffix):
        if domain == "pipeline":
            return f"pipeline-{suffix}"
        return f"{domain}.{suffix}"

    def test_all_fields_follow_saved_environment_default_precedence(self):
        for key, domain in configuration.FIELDS.items():
            saved = self.valid_value(domain, "saved")
            environment = self.valid_value(domain, "environment")
            fallback = self.valid_value(domain, "fallback")
            with self.subTest(key=key), patch.dict(os.environ, {key: environment}):
                self.assertEqual(configuration.get(key, fallback), environment)
                self.db.execute("INSERT OR REPLACE INTO server_settings VALUES (?, ?)",
                                (key, saved))
                self.assertEqual(configuration.get(key, fallback), saved)
                self.db.execute("UPDATE server_settings SET value = '' WHERE key = ?", (key,))
                self.assertEqual(configuration.get(key, fallback), environment)
                self.db.execute("DELETE FROM server_settings WHERE key = ?", (key,))

    def test_all_fields_use_explicit_default_when_environment_is_absent(self):
        for key in configuration.FIELDS:
            with self.subTest(key=key), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(configuration.get(key, "fallback"), "fallback")

    def test_all_fields_export_environment_fallback_for_empty_saved_value(self):
        for key in configuration.FIELDS:
            self.db.execute("INSERT INTO server_settings VALUES (?, ?)", (key, ""))
        environment = {
            key: self.valid_value(domain, "environment")
            for key, domain in configuration.FIELDS.items()
        }
        with patch.dict(os.environ, environment):
            exported = configuration.export()["settings"]
        self.assertEqual(exported, environment)


if __name__ == "__main__":
    unittest.main()
