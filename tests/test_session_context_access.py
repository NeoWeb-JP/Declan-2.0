"""Synchronized session context access regressions."""

import threading
import unittest
from unittest.mock import Mock

from session_context_access import consume_retry_context, load_recent_context


class SessionContextAccessTests(unittest.TestCase):
    def test_recent_context_uses_selected_session_and_scope(self):
        lock = threading.RLock()
        sessions = {"one": {"scope": "kitchen"}}
        retrieve = Mock(return_value=("lights", "device", "info"))
        result = load_recent_context(
            session_id="one", scope="kitchen", sessions=sessions, lock=lock,
            now=15, idle_seconds=300, retrieve=retrieve,
        )
        self.assertEqual(result, ("lights", "device", "info"))
        retrieve.assert_called_once_with(sessions["one"], "kitchen", now=15, idle_seconds=300)

    def test_retry_consumption_uses_session_scope_and_window(self):
        lock = threading.RLock()
        sessions = {"one": {"retry": "pending"}}
        consume = Mock(return_value="pending")
        result = consume_retry_context(
            session_id="one", scope="bedroom", sessions=sessions, lock=lock,
            now=23, window_seconds=90, consume=consume,
        )
        self.assertEqual(result, "pending")
        consume.assert_called_once_with(sessions["one"], "bedroom", now=23, window_seconds=90)

    def test_missing_session_is_forwarded_as_none(self):
        retrieve = Mock(return_value=(None, None, None))
        load_recent_context(
            session_id="missing", scope="lounge", sessions={}, lock=threading.RLock(),
            now=0, idle_seconds=30, retrieve=retrieve,
        )
        retrieve.assert_called_once_with(None, "lounge", now=0, idle_seconds=30)

    def test_invalid_ids_and_corrupt_sessions_are_missing_for_both_paths(self):
        for invalid in (None, [], {}, 42, True, "", "x" * 257):
            with self.subTest(session_id=repr(invalid)):
                self.assert_missing(invalid, {})
        for corrupt in (None, "session", [], 42, True):
            with self.subTest(corrupt=repr(corrupt)):
                self.assert_missing("one", {"one": corrupt})

    def assert_missing(self, session_id, sessions):
        retrieve = Mock(return_value=((), None, None))
        consume = Mock(return_value=None)
        load_recent_context(session_id=session_id, scope="kitchen", sessions=sessions,
                            lock=threading.RLock(), now=10, idle_seconds=30,
                            retrieve=retrieve)
        consume_retry_context(session_id=session_id, scope="kitchen", sessions=sessions,
                              lock=threading.RLock(), now=10, window_seconds=30,
                              consume=consume)
        retrieve.assert_called_once_with(None, "kitchen", now=10, idle_seconds=30)
        consume.assert_called_once_with(None, "kitchen", now=10, window_seconds=30)

    def test_string_subclass_session_id_cannot_execute_custom_hash(self):
        class HostileSessionId(str):
            def __hash__(self):
                raise RuntimeError("untrusted hash")
        self.assert_missing(HostileSessionId("one"), {"one": {"scope": "kitchen"}})

    def test_callback_runs_with_lock_held(self):
        lock = threading.Lock()
        def retrieve(*args, **kwargs):
            self.assertFalse(lock.acquire(blocking=False))
            return (None, None, None)
        load_recent_context(
            session_id="x", scope="x", sessions={}, lock=lock,
            now=1, idle_seconds=1, retrieve=retrieve,
        )


if __name__ == "__main__":
    unittest.main()
