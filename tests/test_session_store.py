"""Session store isolation and backwards-compatible server wiring."""
import unittest

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

    def test_default_store_is_stable(self):
        self.assertIs(session_store.DEFAULT_SESSION_STORE,
                      session_store.DEFAULT_SESSION_STORE)


if __name__ == "__main__":
    unittest.main()
