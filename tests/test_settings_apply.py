"""Verify successful settings imports and recovery snapshots."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from declan.core import configuration


class SettingsApplyTests(unittest.TestCase):
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
    def document(include_learning=False):
        result = {"format": "declan-settings", "schema_version": 1,
                  "settings": {"DECLAN_MOVIE_SCRIPT": "script.new_movie"}}
        if include_learning:
            result["learned_intents"] = {"new phrase": "new target"}
        return result

    def test_apply_updates_settings_and_preserves_learning_when_omitted(self):
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_MOVIE_SCRIPT", "script.old_movie"))
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("existing phrase", "existing target"))
        document = self.document()
        configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(configuration.get("DECLAN_MOVIE_SCRIPT"), "script.new_movie")
        self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                         {"existing phrase": "existing target"})
        snapshot = configuration.recovery(include_learning=True)
        self.assertEqual(snapshot["settings"]["DECLAN_MOVIE_SCRIPT"], "script.old_movie")
        self.assertEqual(snapshot["learned_intents"],
                         {"existing phrase": "existing target"})

    def test_apply_explicit_learning_replaces_existing_aliases(self):
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("existing phrase", "existing target"))
        document = self.document(include_learning=True)
        configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(dict(self.db.execute("SELECT phrase, target FROM learned_intents")),
                         {"new phrase": "new target"})
        self.assertEqual(configuration.recovery(include_learning=True)["learned_intents"],
                         {"existing phrase": "existing target"})

    def test_apply_empty_learning_explicitly_clears_aliases(self):
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("existing phrase", "existing target"))
        document = self.document(include_learning=True)
        document["learned_intents"] = {}
        configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM learned_intents").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
