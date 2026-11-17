"""Verify failed settings writes roll back recovery and previously applied writes."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsWriteRollbackTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.original"))
        self.db.commit()

        @contextmanager
        def database():
            try:
                self.db.execute("BEGIN")
                with self.db:
                    yield self.db
            except BaseException:
                self.db.rollback()
                raise

        self.database_patch = patch.object(configuration.history, "database", database)
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.addCleanup(self.db.close)

    def test_failed_second_setting_rolls_back_first_setting_and_recovery(self):
        document = {
            "format": "declan-settings", "schema_version": 1,
            "settings": {
                "DECLAN_MOVIE_SCRIPT": "script.updated",
                "DECLAN_GOOD_NIGHT_SCRIPT": "script.new_night",
            },
        }
        token = configuration.preview(document)["expected"]
        self.db.execute(
            "CREATE TRIGGER fail_night_setting BEFORE INSERT ON server_settings "
            "WHEN NEW.key = 'DECLAN_GOOD_NIGHT_SCRIPT' "
            "BEGIN SELECT RAISE(ABORT, 'simulated settings write failure'); END"
        )
        self.db.commit()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated settings write failure"):
            configuration.apply(document, token)

        self.assertEqual(
            dict(self.db.execute("SELECT key, value FROM server_settings")),
            {"DECLAN_MOVIE_SCRIPT": "script.original"},
        )
        self.assertIsNone(self.db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'settings_recovery'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
