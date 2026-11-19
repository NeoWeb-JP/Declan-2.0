"""Verify exported settings can be validated, previewed and imported again."""
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsExportRoundTripTests(unittest.TestCase):
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

    def test_export_can_be_validated_and_reimported(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.movie"))
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("movie please", "movie time"))
        with patch.dict(os.environ, {}, clear=True):
            document = configuration.export(include_learning=True)
            self.assertEqual(configuration.validate(document), document)
            self.db.execute("UPDATE server_settings SET value = ? WHERE key = ?",
                            ("script.changed", "DECLAN_MOVIE_SCRIPT"))
            self.db.execute("DELETE FROM learned_intents")
            configuration.apply(document, configuration.preview(document)["expected"])
            self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.movie")
            self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                             {"movie please": "movie time"})

    def test_export_without_learning_preserves_existing_learning_on_import(self):
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("original phrase", "original target"))
        with patch.dict(os.environ, {}, clear=True):
            document = configuration.export()
            self.assertNotIn("learned_intents", document)
            configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                         {"original phrase": "original target"})


if __name__ == "__main__":
    unittest.main()
