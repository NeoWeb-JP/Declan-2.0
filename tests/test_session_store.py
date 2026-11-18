"""Session store isolation and backwards-compatible server wiring."""
import unittest
from unittest.mock import patch

import server

import session_store


class SessionStoreTests(unittest.TestCase):
    def test_instances_have_independent_sessions_and_locks(self):
        first = session_store.SessionStore()
        second = session_store.SessionStore()
        first.sessions["a"] = {"message": "hello"}
        self.assertNotIn("a", second.sessions)
        self.assertIsNot(first.sessions, second.sessions)
        self.assertIsNot(first.lock, second.lock)

    def test_store_lock_protects_mutations(self):
        store = session_store.SessionStore()
        with store.lock:
            store.sessions["session"] = {"turn": 1}
        self.assertEqual(store.sessions["session"]["turn"], 1)

    def test_server_conversation_uses_current_injected_store(self):
        first = session_store.SessionStore()
        second = session_store.SessionStore()
        first.sessions["first"] = {"at": 1}
        second.sessions["second"] = {"at": 2}
        with patch.object(server, "session_orchestration") as orchestration:
            with patch.object(server, "SESSION_STORE", first):
                server.converse("hello", "first")
                self.assertIs(orchestration.converse.call_args.kwargs["sessions"], first.sessions)
            with patch.object(server, "SESSION_STORE", second):
                server.converse("hello", "second")
                self.assertIs(orchestration.converse.call_args.kwargs["sessions"], second.sessions)
        self.assertNotIn("first", second.sessions)

    def test_server_has_no_mutable_session_aliases(self):
        self.assertFalse(hasattr(server, "SESSIONS"))
        self.assertFalse(hasattr(server, "SESSION_LOCK"))

    def test_default_store_is_stable(self):
        self.assertIs(session_store.DEFAULT_SESSION_STORE,
                      session_store.DEFAULT_SESSION_STORE)


if __name__ == "__main__":
    unittest.main()
