"""Shared schema state, migration lifecycle and concurrency regressions."""

import sqlite3
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import history
import timers
from database_schema_state import DatabaseSchemaState
from timer_schema_state import TimerSchemaState


class DatabaseSchemaStateTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "nested" / "state.sqlite3"
        self.state = DatabaseSchemaState()

    def test_timer_adapter_reuses_generic_owner(self):
        self.assertIsInstance(TimerSchemaState(), DatabaseSchemaState)

    def test_failure_does_not_cache_file(self):
        def fail():
            self.path.touch()
            raise sqlite3.OperationalError("database is busy")

        with self.assertRaises(sqlite3.OperationalError):
            self.state.ensure(self.path, fail)
        calls = []
        self.state.ensure(self.path, lambda: calls.append("retry"))
        self.assertEqual(calls, ["retry"])

    def test_concurrent_calls_and_replaced_database(self):
        barrier = threading.Barrier(6)
        calls = []
        errors = []
        gate = threading.Lock()

        def migrate():
            calls.append("migration")
            self.path.touch()

        def worker():
            try:
                barrier.wait(timeout=5)
                self.state.ensure(self.path, migrate)
            except Exception as exc:
                with gate:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(calls, ["migration"])
        self.path.unlink()
        self.state.ensure(self.path, migrate)
        self.assertEqual(len(calls), 2)


class HistorySchemaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "history.sqlite3"
        self.enterContext(patch.object(history, "DATABASE", self.path))
        self.enterContext(patch.object(history, "SCHEMA_STATE", DatabaseSchemaState()))

    def test_legacy_history_migrates_once_and_preserves_turns(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE turns (id INTEGER PRIMARY KEY, created_at REAL, "
                               "session_id TEXT, source TEXT, message TEXT, reply TEXT)")
            connection.execute("INSERT INTO turns VALUES (1, 1, 's', 'assist', 'hello', 'hi')")
        history.initialize()
        history.initialize()
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone(), ("wal",))
            self.assertEqual(connection.execute("SELECT count(*) FROM turns").fetchone(), (1,))
            columns = {row[1] for row in connection.execute("PRAGMA table_info(turns)")}
            self.assertTrue({"outcome", "routine_status", "action_results",
                             "phrase_suggestion", "speaker_match", "diagnostic_id"} <= columns)

    def test_new_database_after_replacement_has_schema(self):
        history.initialize()
        self.path.unlink()
        history.initialize()
        with sqlite3.connect(self.path) as connection:
            self.assertTrue(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'learned_intents'").fetchone())
            self.assertTrue(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'turns'").fetchone())

    def test_failed_history_migration_can_retry(self):
        original = history._migrate_schema
        with patch.object(history, "_migrate_schema", side_effect=sqlite3.OperationalError("busy")):
            with self.assertRaisesRegex(sqlite3.OperationalError, "busy"):
                history.initialize()
        with patch.object(history, "_migrate_schema", wraps=original) as migrate:
            history.initialize()
            history.initialize()
            migrate.assert_called_once()

    def test_timer_and_history_do_not_share_initialization_cache(self):
        with patch.object(timers, "DATABASE", Path(self.folder.name) / "timers.sqlite3"), \
             patch.object(timers, "SCHEMA_STATE", TimerSchemaState()):
            history.initialize()
            timers.initialize()
            self.assertTrue(self.path.exists())
            self.assertTrue(timers.DATABASE.exists())


if __name__ == "__main__":
    unittest.main()
