"""Exports use one environment snapshot for all allowlisted settings."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsExportEnvironmentSnapshotTests(unittest.TestCase):
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

    def test_export_resolves_all_defaults_from_one_snapshot(self):
        snapshot = {key: (f"pipeline-{i}" if domain == "pipeline" else
                          f"{domain}.value_{i}")
                    for i, (key, domain) in enumerate(configuration.FIELDS.items())}
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(configuration, "_environment_snapshot", return_value=snapshot) as read:
                document = configuration.export()
        read.assert_called_once_with()
        self.assertEqual(document["settings"], snapshot)
        self.assertEqual(configuration.validate(document), document)

    def test_saved_nonempty_value_overrides_snapshot(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.saved"))
        snapshot = {key: "" for key in configuration.FIELDS}
        snapshot["DECLAN_MOVIE_SCRIPT"] = "script.environment"
        with patch.object(configuration, "_environment_snapshot", return_value=snapshot):
            exported = configuration.export()
        self.assertEqual(exported["settings"]["DECLAN_MOVIE_SCRIPT"], "script.saved")


if __name__ == "__main__":
    unittest.main()
