"""Voice turn preflight short-circuit regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import turn_preflight as preflight


class TurnPreflightTests(unittest.TestCase):
    def setUp(self):
        self.responses: list[tuple[int, object]]
        self.responses = []
        self.handler = SimpleNamespace(
            log_error=lambda *args: None,
            send_json=lambda status, payload: self.responses.append((status, payload)),
        )
        self.kwargs = dict(
            message="hello", session_id="s", scope="room", source="assist",
            satellite="sat", origin_device="device", sessions={}, lock=object(),
            now=1.0, preprocess=str.lower, normalize=str.lower,
            learned_intent=lambda phrase: None, retry_window=20,
            consume_retry=lambda *args: None, cancel_phrases={"cancel"},
            converse=lambda *args: None, record=lambda *args: None,
            cancel_retry=lambda *args: None, confirm=lambda *args: None,
            evaluate=lambda *args: None, confirmation_response=lambda *args: None,
            guest_commands={}, confirmations={}, diagnostic_id=lambda: None,
            resolve_confirmation=lambda *args: None,
        )

    def test_normal_turn_retains_resolved_values(self):
        with patch.object(preflight.learned_intent_resolution, "resolve", return_value=("effective", "phrase")), patch.object(
            preflight.session_context_access, "consume_retry_context", return_value=None,
        ), patch.object(preflight.sensitive_confirmation_resolution, "resolve_confirmation", return_value=("new", "resolved", "effective", None)):
            result = preflight.resolve(self.handler, {}, **self.kwargs)
        self.assertEqual((result.session_id, result.phrase, result.effective_message), ("new", "resolved", "effective"))
        self.assertEqual(self.responses, [])

    def test_retry_cancellation_skips_confirmation(self):
        self.kwargs["message"] = "cancel"
        cancellation = SimpleNamespace(to_wire=lambda: {"cancelled": True})
        with patch.object(preflight.learned_intent_resolution, "resolve", return_value=("cancel", "cancel")), patch.object(
            preflight.session_context_access, "consume_retry_context", return_value={"pending": True},
        ), patch.object(preflight.retry_cancellation_access, "cancel_pending_retry", return_value=cancellation), patch.object(
            preflight.sensitive_confirmation_resolution, "resolve_confirmation",
        ) as confirmation:
            self.assertIsNone(preflight.resolve(self.handler, {}, **self.kwargs))
            confirmation.assert_not_called()
        self.assertEqual(self.responses, [(200, {"cancelled": True})])

    def test_confirmation_reply_stops_dispatch(self):
        with patch.object(preflight.learned_intent_resolution, "resolve", return_value=("hello", "hello")), patch.object(
            preflight.session_context_access, "consume_retry_context", return_value=None,
        ), patch.object(preflight.sensitive_confirmation_resolution, "resolve_confirmation", return_value=("s", "hello", "hello", {"confirmed": True})):
            self.assertIsNone(preflight.resolve(self.handler, {}, **self.kwargs))
        self.assertEqual(self.responses, [(200, {"confirmed": True})])


if __name__ == "__main__":
    unittest.main()
