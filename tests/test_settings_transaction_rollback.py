"""Verify failed settings imports roll back settings, learning and recovery together."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsTransactionRollbackTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.original"))
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("old phrase", "old target"))
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

    def test_failed_learning_insert_rolls_back_every_import_write(self):
        document = {
            "format": "declan-settings", "schema_version": 1,
            "settings": {"DECLAN_MOVIE_SCRIPT": "script.replacement"},
            "learned_intents": {"new phrase": "new target"},
        }
        token = configuration.preview(document)["expected"]
        self.db.execute(
            "CREATE TRIGGER fail_new_learning BEFORE INSERT ON learned_intents "
            "BEGIN SELECT RAISE(ABORT, 'simulated learning write failure'); END"
        )
        self.db.commit()

        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated learning write failure"):
            configuration.apply(document, token)

        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.original")
        self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                         {"old phrase": "old target"})
        self.assertIsNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings_recovery'"
        ).fetchone())


if __name__ == "__main__":
    unittest.main()
