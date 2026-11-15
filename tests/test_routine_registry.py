"""Routine registry validation and persistence tests."""
import unittest
from unittest.mock import patch
import sqlite3
import tempfile
from pathlib import Path
import routine_registry

class RegistryTests(unittest.TestCase):
    def sample(self):
        return {"movie": {"script": "script.movie_time", "phrases": ["start movie time", "cinema time"], "fields": {"requested_action": "start"}, "sensitive": False}}

    def test_valid_fixed_and_parameterised(self):
        self.assertEqual(routine_registry.validate(self.sample()), self.sample())
        fixed = self.sample()
        fixed["movie"]["fields"] = {}
        self.assertEqual(routine_registry.validate(fixed), fixed)

    def test_invalid_script_and_field_rejected(self):
        value = self.sample()
        value["movie"]["script"] = "automation.bad"
        with self.assertRaises(ValueError):
            routine_registry.validate(value)
        value = self.sample()
        value["movie"]["fields"] = {"entity_id": ["script.evil"]}
        with self.assertRaises(ValueError):
            routine_registry.validate(value)

    def test_duplicate_phrase_rejected(self):
        value = self.sample()
        value["another"] = {"script": "script.another", "phrases": ["cinema time"], "fields": {}, "sensitive": True}
        with self.assertRaises(ValueError):
            routine_registry.validate(value)

    def test_parameterised_phrase_and_action_allowlist(self):
        value = self.sample()
        value["movie"]["phrases"] = ["start {room} cinema with {mode}", "{action} cinema"]
        routine_registry.validate(value)
        with patch.object(routine_registry, "load", return_value=value):
            self.assertEqual(routine_registry.match("start kitchen cinema with dark")[2], {"room": "kitchen", "mode": "dark"})
            self.assertIsNone(routine_registry.match("delete cinema"))
            self.assertEqual(routine_registry.match("end cinema")[2]["action"], "end")

    def test_bootstrap_imports_only_existing_scripts_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "bootstrap.db")
            from contextlib import contextmanager
            @contextmanager
            def db():
                connection = sqlite3.connect(path)
                try:
                    yield connection
                    connection.commit()
                finally:
                    connection.close()
            with patch.object(routine_registry.history, "database", side_effect=db), patch(
                "configuration.get", side_effect=lambda key, default="": {
                    "DECLAN_MOVIE_SCRIPT": "script.movie_time",
                    "DECLAN_GOOD_MORNING_SCRIPT": "script.old_morning"
                }.get(key, default)
            ):
                first = routine_registry.bootstrap({"script.movie_time", "script.old_morning"})
                self.assertEqual(first["movie"]["script"], "script.movie_time")
                self.assertEqual(first["morning"]["script"], "script.old_morning")
                self.assertNotIn("night", first)
                self.assertEqual(routine_registry.bootstrap(set()), first)
                self.assertEqual(routine_registry.load(), first)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "test.db")
            class Database:
                def __enter__(self):
                    self.db = sqlite3.connect(path)
                    return self.db
                def __exit__(self, kind, value, trace):
                    if kind is None:
                        self.db.commit()
                    self.db.close()
            with patch.object(routine_registry.history, "database", side_effect=Database):
                routine_registry.save(self.sample())
                self.assertEqual(routine_registry.load(), self.sample())
                self.assertEqual(routine_registry.match("cinema time")[0], "movie")

if __name__ == "__main__":
    unittest.main()
