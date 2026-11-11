import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import history


class HistoryConcurrencyTests(TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(history, "DATABASE", root / "history.sqlite3"))

    def test_migrates_legacy_database_once_and_uses_wal(self):
        with closing(sqlite3.connect(history.DATABASE)) as db, db:
            db.execute("CREATE TABLE turns (id INTEGER PRIMARY KEY, created_at REAL, session_id TEXT, "
                       "source TEXT, message TEXT, reply TEXT)")
            db.execute("INSERT INTO turns VALUES (1, 1, 's', 'assist', 'old', 'reply')")
        history.initialize()
        with history.database() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone(), ("wal",))
            db.execute("INSERT INTO learned_intents VALUES ('miss', 'hello')")
        with patch.object(history.sqlite3, "connect", wraps=sqlite3.connect) as connect:
            self.assertEqual(history.learned_intent('miss'), 'hello')
            self.assertEqual(len(history.recent()), 1)  # Reads must not prune old turns.
            self.assertEqual(connect.call_count, 2)
        history.prune()
        self.assertEqual(history.recent(), [])

    def test_lookup_succeeds_while_another_connection_holds_write_lock(self):
        history.initialize()
        with history.database() as db:
            db.execute("INSERT INTO learned_intents VALUES ('miss', 'hello')")
        writer = sqlite3.connect(history.DATABASE)
        self.addCleanup(writer.close)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE learned_intents SET target = 'pending' WHERE phrase = 'miss'")
        self.assertEqual(history.learned_intent('miss'), 'hello')
        self.assertEqual(history.learned_intents(), {'miss': 'hello'})

    def test_ordinary_reads_issue_no_ddl_write_transaction_or_delete(self):
        history.initialize()
        statements = []
        connect = sqlite3.connect
        def traced(*args, **kwargs):
            db = connect(*args, **kwargs)
            db.set_trace_callback(statements.append)
            return db
        with patch.object(history.sqlite3, 'connect', side_effect=traced):
            history.learned_intent('missing')
            history.recent()
        self.assertTrue(statements)
        self.assertTrue(all(s.startswith('SELECT') for s in statements), statements)
