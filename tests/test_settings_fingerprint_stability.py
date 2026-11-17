"""Verify deterministic preview fingerprints and learning state invalidation."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import configuration


class SettingsFingerprintTests(unittest.TestCase):
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
    def document():
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {"DECLAN_MOVIE_SCRIPT": "script.movie"}}

    def test_unchanged_state_produces_repeatable_preview(self):
        document = self.document()
        self.assertEqual(configuration.preview(document)["expected"],
                         configuration.preview(document)["expected"])

    def test_preview_fingerprint_is_independent_of_document_key_order(self):
        first = self.document()
        reordered = {"settings": first["settings"], "schema_version": 1,
                     "format": "declan-settings"}
        self.assertEqual(configuration.preview(first)["expected"],
                         configuration.preview(reordered)["expected"])

    def test_learned_intent_change_invalidates_preview(self):
        document = self.document()
        token = configuration.preview(document)["expected"]
        self.db.execute("INSERT INTO learned_intents VALUES (?, ?)",
                        ("lights please", "turn on lights"))
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(document, token)

    def test_unrelated_saved_setting_change_invalidates_preview(self):
        document = self.document()
        token = configuration.preview(document)["expected"]
        self.db.execute("INSERT INTO server_settings VALUES (?, ?)",
                        ("DECLAN_WEB_ASSIST_PIPELINE", "pipeline-one"))
        with self.assertRaisesRegex(ValueError, "Preview the file again"):
            configuration.apply(document, token)


if __name__ == "__main__":
    unittest.main()
