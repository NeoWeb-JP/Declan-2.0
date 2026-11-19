"""The environment checked by a preview token is the environment saved for recovery."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsVerifiedEnvironmentTests(unittest.TestCase):
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

    def test_recovery_uses_verified_environment_even_if_environment_changes_during_import(self):
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": "script.new"}}
        with patch.dict(os.environ, {"DECLAN_MOVIE_SCRIPT": "script.verified"}):
            token = configuration.preview(document)["expected"]
            original = configuration._environment_snapshot

            def snapshot_then_change():
                snapshot = original()
                os.environ["DECLAN_MOVIE_SCRIPT"] = "script.changed_after_check"
                return snapshot

            with patch.object(configuration, "_environment_snapshot", side_effect=snapshot_then_change):
                configuration.apply(document, token)
            recovery = configuration.recovery()
        self.assertEqual(recovery["settings"]["DECLAN_MOVIE_SCRIPT"], "script.verified")


if __name__ == "__main__":
    unittest.main()
