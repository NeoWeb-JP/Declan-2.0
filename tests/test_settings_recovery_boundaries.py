"""Verify settings recovery availability and learned-intention opt-in."""
import json
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsRecoveryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")

        @contextmanager
        def database():
            yield self.db

        self.patch = patch.object(configuration.history, "database", database)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.db.close)

    def test_missing_recovery_table_is_reported(self):
        with self.assertRaisesRegex(ValueError, "No previous settings import"):
            configuration.recovery()

    def test_empty_recovery_table_is_reported(self):
        self.db.execute("CREATE TABLE settings_recovery (id INTEGER PRIMARY KEY, document TEXT)")
        with self.assertRaisesRegex(ValueError, "No previous settings import"):
            configuration.recovery()

    def test_recovery_excludes_learning_by_default(self):
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": "script.movie"},
                    "learned_intents": {"play movie": "movie time"}}
        self.db.execute("CREATE TABLE settings_recovery (id INTEGER PRIMARY KEY, document TEXT)")
        self.db.execute("INSERT INTO settings_recovery VALUES (?, ?)", (1, json.dumps(document)))
        result = configuration.recovery()
        self.assertEqual(result["settings"], document["settings"])
        self.assertNotIn("learned_intents", result)
        self.assertEqual(configuration.recovery(include_learning=True), document)

    def test_unrelated_recovery_rows_are_not_selected(self):
        self.db.execute("CREATE TABLE settings_recovery (id INTEGER PRIMARY KEY, document TEXT)")
        self.db.execute("INSERT INTO settings_recovery VALUES (?, ?)", (2, "{}"))
        with self.assertRaisesRegex(ValueError, "No previous settings import"):
            configuration.recovery()


if __name__ == "__main__":
    unittest.main()
