"""Regression tests for extracted conversation session orchestration."""
import re
import unittest
from collections import OrderedDict
from unittest.mock import patch

import session_orchestration


class SessionOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.sessions = OrderedDict()
        self.kwargs = dict(
            sessions=self.sessions, idle_seconds=300,
            name_pattern=re.compile(r"my name is ([a-z]+)", re.I),
            chat_commands={"what's my name": "recall_name", "what did i say": "recall_message"},
            unmatched_reply="Unmatched", decorate=lambda reply, category, guest: reply,
        )

    def test_name_and_last_message_are_scoped_to_session(self):
        first = session_orchestration.converse("my name is Alex", None, **self.kwargs)
        sid = first["session_id"]
        self.assertEqual(session_orchestration.converse("what's my name", sid, **self.kwargs)["reply"], "Your name is Alex.")
        other = session_orchestration.converse("what's my name", None, **self.kwargs)
        self.assertEqual(other["reply"], "I don't know your name yet.")
        self.assertNotEqual(other["session_id"], sid)

    def test_routine_reply_and_context_are_retained(self):
        first = session_orchestration.converse("lights on", None, "Done",
                                              lighting_context=("light.study",), scope="kitchen", **self.kwargs)
        self.assertEqual(first["reply"], "Done")
        self.assertEqual(self.sessions[first["session_id"]]["lighting_context"], ("light.study",))
        self.assertEqual(self.sessions[first["session_id"]]["lighting_scope"], "kitchen")

    def test_expired_sessions_are_removed(self):
        self.sessions["expired"] = {"at": 0, "last": "old", "name": "Alex"}
        with patch.object(session_orchestration, "monotonic", return_value=400):
            result = session_orchestration.converse("what's my name", "expired", **self.kwargs)
        self.assertNotEqual(result["session_id"], "expired")
        self.assertNotIn("expired", self.sessions)

    def test_hostile_string_session_id_is_not_hashed_or_reused(self):
        class HostileId(str):
            def __hash__(self):
                raise RuntimeError("unsafe hash")
        self.sessions["known"] = {"at": 0, "name": "Alex"}
        result = session_orchestration.converse("what's my name", HostileId("known"),
                                                **self.kwargs)
        self.assertNotEqual(result["session_id"], "known")
        self.assertEqual(result["reply"], "I don't know your name yet.")

    def test_invalid_session_ids_receive_new_opaque_ids(self):
        for invalid in (None, [], 42, True, "", "x" * 257):
            with self.subTest(value=repr(invalid)):
                result = session_orchestration.converse("hello", invalid, **self.kwargs)
                self.assertIs(type(result["session_id"]), str)
                self.assertNotEqual(result["session_id"], invalid)

    def test_session_count_is_bounded(self):
        for index in range(130):
            session_orchestration.converse("hello", None, **self.kwargs)
        self.assertEqual(len(self.sessions), 128)


if __name__ == "__main__":
    unittest.main()
