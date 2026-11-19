"""Conversation session entry preserves the initialization contract."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from declan.turn import turn_session_entry


class TurnSessionEntryTests(unittest.TestCase):
    def setUp(self):
        self.handler = SimpleNamespace(path="/api/chat")
        self.store = SimpleNamespace(sessions={}, lock=object())
        self.deps = dict(
            message="hello", session_id="old",
            arbiter=MagicMock(), normalize=MagicMock(),
            new_session_id=MagicMock(), session_store=self.store,
            now=123.5, idle_seconds=120, retrieve=MagicMock(),
        )

    def test_preserves_all_session_dependencies(self):
        body = {"message": "hello"}
        expected = SimpleNamespace(session_id="new")
        with patch.object(turn_session_entry.turn_initialization, "prepare", return_value=expected) as prepare:
            self.assertIs(turn_session_entry.prepare(self.handler, body, **self.deps), expected)
        prepare.assert_called_once_with(
            self.handler, body, message="hello", session_id="old",
            arbiter=self.deps["arbiter"], normalize=self.deps["normalize"],
            new_session_id=self.deps["new_session_id"],
            sessions=self.store.sessions, lock=self.store.lock,
            now=123.5, idle_seconds=120, retrieve=self.deps["retrieve"],
        )

    def test_none_turn_is_preserved(self):
        with patch.object(turn_session_entry.turn_initialization, "prepare", return_value=None):
            self.assertIsNone(turn_session_entry.prepare(self.handler, {}, **self.deps))

    def test_session_initialization_errors_are_not_swallowed(self):
        with patch.object(turn_session_entry.turn_initialization, "prepare", side_effect=ValueError("bad session")):
            with self.assertRaisesRegex(ValueError, "bad session"):
                turn_session_entry.prepare(self.handler, {}, **self.deps)

    def test_session_store_is_read_at_call_time(self):
        with patch.object(turn_session_entry.turn_initialization, "prepare") as prepare:
            replacement = {"new": object()}
            self.store.sessions = replacement
            turn_session_entry.prepare(self.handler, {}, **self.deps)
        self.assertIs(prepare.call_args.kwargs["sessions"], replacement)


if __name__ == "__main__":
    unittest.main()
