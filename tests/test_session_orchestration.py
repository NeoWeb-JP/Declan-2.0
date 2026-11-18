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

    def test_injected_clock_and_identity_factory(self):
        result = session_orchestration.converse(
            "hello", None, clock=lambda: 123, new_session_id=lambda: "injected-id",
            **self.kwargs)
        self.assertEqual(result["session_id"], "injected-id")
        self.assertEqual(self.sessions["injected-id"]["at"], 123)

    def test_invalid_clock_fails_without_mutating_sessions(self):
        self.sessions["known"] = {"at": 100, "name": "Alex"}
        for now in (None, True, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(now=repr(now)):
                with self.assertRaises(ValueError):
                    session_orchestration.converse("hello", "known",
                        clock=lambda value=now: value, **self.kwargs)
                self.assertIn("known", self.sessions)

    def test_invalid_idle_window_drops_stale_context(self):
        self.sessions["known"] = {"at": 100, "name": "Alex"}
        kwargs = {**self.kwargs, "idle_seconds": float("nan")}
        result = session_orchestration.converse(
            "what's my name", "known", clock=lambda: 101, **kwargs)
        self.assertNotEqual(result["session_id"], "known")
        self.assertEqual(result["reply"], "I don't know your name yet.")

    def test_invalid_lighting_origin_is_not_stored(self):
        for scope in (None, "  ", ("assist", None, None, None)):
            with self.subTest(scope=scope):
                result = session_orchestration.converse(
                    "lights on", None, "Done", lighting_context=("light.study",),
                    scope=scope, **self.kwargs)
                self.assertNotIn("lighting_context", self.sessions[result["session_id"]])

    def test_generated_session_ids_must_be_valid_and_unique(self):
        self.sessions["existing"] = {"at": 10, "name": "Alex"}
        for generated in (None, "", 12, True, "x" * 257, "existing"):
            with self.subTest(generated=repr(generated)):
                with self.assertRaises(ValueError):
                    session_orchestration.converse(
                        "hello", None, clock=lambda: 11,
                        new_session_id=lambda value=generated: value, **self.kwargs)
                self.assertEqual(self.sessions["existing"]["name"], "Alex")

    def test_local_time_is_injected_only_for_time_reply(self):
        from datetime import datetime
        calls = []
        def local_time():
            calls.append(True)
            return datetime(2026, 11, 18, 14, 35)
        kwargs = {**self.kwargs, "chat_commands": {"what time": "time"}}
        result = session_orchestration.converse(
            "what time", None, local_time=local_time, **kwargs)
        self.assertEqual(result["reply"], "It's 14:35 here.")
        self.assertEqual(len(calls), 1)
        session_orchestration.converse("hello", None, local_time=local_time, **kwargs)
        self.assertEqual(len(calls), 1)

    def test_restored_recall_never_restores_action_context(self):
        from unittest.mock import Mock
        recall = Mock()
        recall.restore.return_value = {
            "name": "Alex", "recent_messages": ["hello"],
            "last": "turn off the lights",
            "lighting_context": ("light.kitchen",), "lighting_scope": "kitchen",
            "pending_retry": {"text": "turn off lights", "scope": "kitchen", "at": 10},
            "device_status_target": "lock.front_door",
        }
        result = session_orchestration.converse(
            "what's my name", "recalled", recall=recall,
            clock=lambda: 100, **self.kwargs)
        self.assertEqual(result["reply"], "Your name is Alex.")
        state = self.sessions[result["session_id"]]
        for key in ("lighting_context", "lighting_scope", "pending_retry",
                    "device_status_target"):
            self.assertNotIn(key, state)
        self.assertEqual(state["recent_messages"], ["hello", "what's my name"])

    def test_hostile_message_is_rejected_before_string_methods(self):
        class HostileText(str):
            def casefold(self):
                raise RuntimeError("untrusted string method")
        with self.assertRaises(ValueError):
            session_orchestration.converse(HostileText("hello"), None, **self.kwargs)
        self.assertFalse(self.sessions)

    def test_failed_reply_does_not_remove_existing_session(self):
        first = session_orchestration.converse(
            "my name is Alex", None, clock=lambda: 100, **self.kwargs)
        sid = first["session_id"]
        def fail_decorate(reply, category, guest):
            raise RuntimeError("formatter unavailable")
        kwargs = {**self.kwargs, "decorate": fail_decorate}
        with self.assertRaisesRegex(RuntimeError, "formatter unavailable"):
            session_orchestration.converse(
                "what's my name", sid, clock=lambda: 101, **kwargs)
        self.assertIn(sid, self.sessions)
        self.assertEqual(self.sessions[sid]["name"], "Alex")

    def test_failed_recall_restore_does_not_remove_active_session(self):
        from unittest.mock import Mock
        recall = Mock()
        recall.restore.side_effect = RuntimeError("recall unavailable")
        first = session_orchestration.converse(
            "my name is Alex", None, clock=lambda: 100, **self.kwargs)
        sid = first["session_id"]
        result = session_orchestration.converse(
            "what's my name", sid, clock=lambda: 101,
            recall=recall, **self.kwargs)
        self.assertEqual(result["reply"], "Your name is Alex.")
        recall.restore.assert_not_called()

    def test_subclassed_restored_state_is_not_accepted(self):
        from unittest.mock import Mock
        class UntrustedState(dict):
            def get(self, key, default=None):
                raise RuntimeError("untrusted get")
        recall = Mock()
        recall.restore.return_value = UntrustedState(name="Alex")
        result = session_orchestration.converse(
            "what's my name", "expired", recall=recall,
            clock=lambda: 100, **self.kwargs)
        self.assertEqual(result["reply"], "I don't know your name yet.")
        self.assertNotEqual(result["session_id"], "expired")

    def test_session_count_is_bounded(self):
        for index in range(130):
            session_orchestration.converse("hello", None, **self.kwargs)
        self.assertEqual(len(self.sessions), 128)


if __name__ == "__main__":
    unittest.main()
