"""Regression tests for grouped ingress turn stages."""
import unittest
from unittest.mock import Mock

from ingress_turn_orchestration import (
    resolve_origin, resolve_learned_message, consume_retry, resolve_confirmation,
)


class IngressTurnOrchestrationTests(unittest.TestCase):
    def test_origin_preserves_source_and_scope(self):
        resolve = Mock(return_value=("assist", "kitchen", "device", "sat"))
        self.assertEqual(resolve_origin("/api/assist", {"a": 1}, resolve=resolve),
                         ("assist", "kitchen", "device", "sat"))
        resolve.assert_called_once_with("/api/assist", {"a": 1})

    def test_learned_intent_preserves_dependencies(self):
        resolve = Mock(return_value=("corrected", "phrase"))
        dependencies = {name: Mock() for name in (
            "preprocess", "normalize", "learned_intent", "log_error",
        )}
        self.assertEqual(resolve_learned_message(
            "spoken", resolve=resolve, **dependencies,
        ), ("corrected", "phrase"))
        resolve.assert_called_once_with("spoken", **dependencies)

    def test_retry_preserves_lock_and_time_window(self):
        consume_context = Mock(return_value="pending")
        deps = dict(session_id="session", scope="room", sessions={},
                    lock=Mock(), now=10, window_seconds=30, consume=Mock())
        self.assertEqual(consume_retry(
            consume_context=consume_context, **deps,
        ), "pending")
        consume_context.assert_called_once_with(**deps)

    def test_confirmation_resolves_once_with_original_phrase(self):
        confirm = Mock(return_value="decision")
        resolve = Mock(return_value=("new-session", "yes", "yes", {"reply": "ok"}))
        deps = {name: Mock() for name in (
            "evaluate", "confirmation_response", "normalize", "record",
            "diagnostic_id", "log_error",
        )}
        result = resolve_confirmation(
            "yes", "original", "session", confirm=confirm, resolve=resolve,
            source="assist", satellite="sat", origin_device="kitchen",
            speaker="speaker", guest_commands={"guest"}, confirmations={},
            effective_message="original", **deps,
        )
        self.assertEqual(result[0], "new-session")
        confirm.assert_called_once_with(
            "yes", "original", "session", source="assist", satellite="sat",
            origin_device="kitchen", speaker="speaker",
            guest_commands={"guest"}, confirmations={}, **deps,
        )
        resolve.assert_called_once_with("decision", "original", "original")


if __name__ == "__main__":
    unittest.main()
