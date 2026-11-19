"""Preflight entry preserves session-store identity and existing results."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from declan.turn import turn_preflight_entry


class TurnPreflightEntryTests(unittest.TestCase):
    def test_forwards_live_sessions_and_lock_without_mutation(self):
        sessions = {"session": object()}
        lock = object()
        store = SimpleNamespace(sessions=sessions, lock=lock)
        handler = object()
        body = {"message": "hello"}
        result = object()
        with patch.object(turn_preflight_entry.turn_preflight, "resolve", return_value=result) as resolve:
            self.assertIs(turn_preflight_entry.resolve(
                handler, body, session_store=store,
                message="hello", session_id="session", now=1.25,
            ), result)
        resolve.assert_called_once_with(
            handler, body, sessions=sessions, lock=lock,
            message="hello", session_id="session", now=1.25,
        )

    def test_none_preflight_is_preserved(self):
        store = SimpleNamespace(sessions={}, lock=object())
        with patch.object(turn_preflight_entry.turn_preflight, "resolve", return_value=None):
            self.assertIsNone(turn_preflight_entry.resolve(object(), {}, session_store=store))

    def test_preflight_errors_propagate(self):
        store = SimpleNamespace(sessions={}, lock=object())
        with patch.object(turn_preflight_entry.turn_preflight, "resolve", side_effect=ValueError("invalid")):
            with self.assertRaisesRegex(ValueError, "invalid"):
                turn_preflight_entry.resolve(object(), {}, session_store=store)

    def test_reads_replaced_session_mapping_on_each_request(self):
        store = SimpleNamespace(sessions={}, lock=object())
        with patch.object(turn_preflight_entry.turn_preflight, "resolve") as resolve:
            store.sessions = {"new": object()}
            turn_preflight_entry.resolve(object(), {}, session_store=store)
        self.assertIs(resolve.call_args.kwargs["sessions"], store.sessions)


if __name__ == "__main__":
    unittest.main()
