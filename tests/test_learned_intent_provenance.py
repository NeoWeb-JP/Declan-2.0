"""#98: learned phrases record when and how they were trained, and Settings lists them all."""
import sqlite3
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from declan.core import configuration, history
from declan.http import native_read_routes

ROOT = Path(__file__).resolve().parents[1]


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(history, "DATABASE", root / "history.sqlite3"))

    def records(self):
        return {row["phrase"]: row for row in history.learned_intent_records()}

    def test_legacy_rows_survive_migration_without_provenance(self):
        with closing(sqlite3.connect(history.DATABASE)) as db, db:
            db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
            db.execute("INSERT INTO learned_intents VALUES ('old', 'good morning')")
        history.initialize()
        with history.database() as db:
            # Positional two-column inserts (settings import, older releases) still work.
            db.execute("INSERT INTO learned_intents VALUES ('older', 'good night')")
        self.assertEqual(self.records()["old"], {"phrase": "old", "target": "good morning",
                                                 "trained_at": None, "source": None})
        self.assertEqual(history.learned_intents(), {"old": "good morning", "older": "good night"})

    def test_each_training_path_records_its_source(self):
        history.teach_phrase("lights please", "turn on the lights")
        history.teach_phrase("tunes", "play music", automatic=True)
        with history.database() as db:
            turn = db.execute("INSERT INTO turns(created_at, session_id, source, message, reply) "
                              "VALUES (strftime('%s','now'), 's', 'assist', 'dimmer', 'x')").lastrowid
        history.teach_intent(turn, "dim the lights", "x")
        records = self.records()
        self.assertEqual(records["lights please"]["source"], "recording")
        self.assertEqual(records["tunes"]["source"], "retry")
        self.assertEqual(records["dimmer"]["source"], "history")
        self.assertTrue(records["tunes"]["trained_at"].endswith("+00:00"))
        history.edit_intent("tunes", "play some music", "play music")
        self.assertEqual(self.records()["tunes"]["source"], "edited")

    def test_automatic_retry_never_overwrites_explicit_provenance(self):
        history.teach_phrase("tunes", "play music")
        history.teach_phrase("tunes", "play radio", automatic=True)
        self.assertEqual(self.records()["tunes"]["source"], "recording")
        self.assertEqual(history.learned_intent("tunes"), "play music")

    def test_forget_removes_provenance(self):
        history.teach_phrase("tunes", "play music")
        history.forget_intent("tunes")
        with history.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM learned_intent_provenance").fetchone(), (0,))

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            history.teach_phrase("tunes", "play music", source="other")

    def test_settings_import_marks_phrases_imported(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE server_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("CREATE TABLE learned_intents (phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
        db.execute("INSERT INTO learned_intents VALUES ('stale', 'play music')")

        @contextmanager
        def database():
            yield db
        document = {"format": "declan-settings", "schema_version": 1,
                    "settings": {"DECLAN_MOVIE_SCRIPT": "script.new_movie"},
                    "learned_intents": {"fresh": "good morning"}}
        with patch.object(configuration.history, "database", database):
            configuration.apply(document, configuration.preview(document)["expected"])
        self.assertEqual(dict(db.execute("SELECT phrase, target FROM learned_intents")), {"fresh": "good morning"})
        self.assertEqual(db.execute("SELECT phrase, source FROM learned_intent_provenance").fetchall(),
                         [("fresh", "imported")])

    def test_native_route_returns_details(self):
        history.teach_phrase("tunes", "play music")
        sent = []
        handler = SimpleNamespace(path="/api/native/intents",
                                  send_json=lambda status, payload: sent.append((status, payload)))
        native_read_routes.dispatch(handler, **{name: None for name in native_read_routes.dispatch.__code__.co_varnames[
            1:native_read_routes.dispatch.__code__.co_argcount + native_read_routes.dispatch.__code__.co_kwonlyargcount]
            if name != "history"}, history=history)
        status, payload = sent[-1]
        self.assertEqual(status, 200)
        self.assertEqual(payload["intents"], {"tunes": "play music"})
        self.assertEqual(payload["details"]["tunes"]["source"], "recording")


class PanelTests(unittest.TestCase):
    def test_learned_commands_are_back_in_settings(self):
        js = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
        voice = js.split('settings-section--voice', 1)[1].split('settings-section--music', 1)[0]
        for needle in ('class="intents-list"', 'class="intents-status', 'class="intents-filter"', "Learned commands"):
            self.assertIn(needle, voice)
        self.assertIn("void this.loadLearnedIntents();", js)
        self.assertIn("filterLearnedIntents()", js)
        self.assertIn("Learned before training dates were recorded.", js)

    def test_proxy_passes_only_known_provenance(self):
        source = (ROOT / "custom_components/declan_two/management_view.py").read_text()
        self.assertIn('{"history", "recording", "retry", "edited", "imported", "conversation"}', source)
        self.assertIn('"details": details', source)


if __name__ == "__main__":
    unittest.main()
