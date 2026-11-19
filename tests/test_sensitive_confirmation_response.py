"""Sensitive confirmation response and persistence regression tests."""
import sqlite3
import unittest
from unittest.mock import Mock
from sensitive_confirmation_response import confirmation_response
from sensitive_confirmation_response import confirmation_reply_result
from confirmation_results import ConfirmationDecision
from execution_results import Outcome


class ConfirmationResponseTests(unittest.TestCase):
    def test_reply_results_retain_typed_outcomes_until_serialization(self):
        decision: object
        expected = {ConfirmationDecision.PROMPT: Outcome.CONFIRMATION_PROMPT,
                    ConfirmationDecision.CANCELLED: Outcome.CONFIRMATION_CANCELLED,
                    ConfirmationDecision.DENIED: Outcome.CONFIRMATION_DENIED}
        for decision in ConfirmationDecision:
            with self.subTest(decision=decision):
                result = confirmation_reply_result(decision)
                self.assertEqual(result, confirmation_reply_result(decision.value))
                if decision not in expected:
                    self.assertIsNone(result)
                    continue
                assert result is not None
                self.assertIs(result.outcome, expected[decision])
                self.assertIs(result.continue_conversation, decision is ConfirmationDecision.PROMPT)
                with self.assertRaises(AttributeError):
                    setattr(result, "outcome", Outcome.CONFIRMED)
                wire = result.to_wire("session-1")
                self.assertIs(type(wire["outcome"]), str)
                self.assertEqual(self.response(decision), wire)
                self.assertIs(type(self.record.call_args.args[4]), str)
        for decision in (None, [], {}, "PROMPT", " prompt", "future"):
            self.assertIsNone(confirmation_reply_result(decision))

    def setUp(self):
        self.record = Mock()
        self.diagnostic_id = Mock(return_value="trace-1")
        self.log_error = Mock()

    def response(self, decision):
        return confirmation_response(decision, "session-1", source="assist",
            message="assign guests", speaker="Jaco", record=self.record,
            diagnostic_id=self.diagnostic_id, log_error=self.log_error)

    def test_prompt_keeps_conversation_open(self):
        result = self.response("prompt")
        self.assertTrue(result["continue_conversation"])
        self.assertEqual(result["outcome"], "confirmation_prompt")
        self.assertIn("30 seconds", result["reply"])

    def test_cancelled_stops_conversation(self):
        result = self.response("cancelled")
        self.assertFalse(result["continue_conversation"])
        self.assertEqual(result["reply"], "Cancelled. Nothing has been run.")

    def test_denied_stops_conversation(self):
        result = self.response("denied")
        self.assertFalse(result["continue_conversation"])
        self.assertEqual(result["outcome"], "confirmation_denied")

    def test_history_records_speaker_and_diagnostic(self):
        result = self.response("prompt")
        self.record.assert_called_once_with(
            "session-1", "assist", "assign guests", result["reply"],
            "confirmation_prompt", speaker="Jaco", diagnostic_id="trace-1")

    def test_confirmed_has_no_response_or_history(self):
        self.assertIsNone(self.response("confirmed"))
        self.record.assert_not_called()
        self.diagnostic_id.assert_not_called()

    def test_unknown_decision_has_no_response(self):
        self.assertIsNone(self.response("continue"))
        self.record.assert_not_called()

    def test_sqlite_history_failure_is_nonfatal(self):
        self.record.side_effect = sqlite3.Error("unavailable")
        self.assertFalse(self.response("prompt")["history_saved"])
        self.log_error.assert_called_once()

    def test_os_history_failure_is_nonfatal(self):
        self.record.side_effect = OSError("disk full")
        self.assertFalse(self.response("denied")["history_saved"])

    def test_success_does_not_mark_history_failed(self):
        self.assertNotIn("history_saved", self.response("prompt"))
