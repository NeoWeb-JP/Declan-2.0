"""Typed retry cancellation and roast/guest results preserve API semantics."""
import sqlite3
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
from declan.turn import retry_cancellation
from declan.turn import roast_command_dispatch
from declan.turn import roast_guest_dispatch


class TypedRetryRoastResultTests(unittest.TestCase):
    def test_cancellation_preserves_session_metadata_and_plain_wire_history_values(self):
        session = {"session_id": "new-session", "reply": "", "custom": "metadata"}
        converse = Mock(return_value=session)
        record = Mock()
        with patch.object(retry_cancellation, "cancel_retry", side_effect=AssertionError("legacy cancellation")):
            result = retry_cancellation.cancel_retry_result(
                "cancel", "old-session", scope="kitchen", source="assist", speaker="speaker",
                converse=converse, record=record, log_error=Mock())
        self.assertIs(result.result.outcome, Outcome.CANCELLED)
        wire = result.to_wire()
        self.assertEqual(wire["custom"], "metadata")
        self.assertEqual(wire["session_id"], "new-session")
        self.assertEqual(wire["reply"], "")
        self.assertFalse(wire["continue_conversation"])
        self.assertIs(type(wire["outcome"]), str)
        self.assertNotIn("outcome", session)
        record.assert_called_once_with("new-session", "assist", "cancel", "", "cancelled", speaker="speaker")
        self.assertIs(type(record.call_args.args[4]), str)
        converse.assert_called_once_with("cancel", "old-session", "", scope="kitchen")
        with self.assertRaises(FrozenInstanceError):
            result.history_saved = False

    def test_cancellation_persistence_failure_remains_nonfatal_and_source_scoped(self):
        for failure in (OSError("disk"), sqlite3.Error("locked")):
            record = Mock(side_effect=failure)
            log = Mock()
            result = retry_cancellation.cancel_retry_result(
                "cancel", "session", scope="kitchen", source="browser_voice", speaker="private",
                converse=Mock(return_value={"session_id": "session", "reply": ""}),
                record=record, log_error=log)
            self.assertIs(result.result.outcome, Outcome.CANCELLED)
            self.assertFalse(result.history_saved)
            self.assertFalse(result.to_wire()["history_saved"])
            self.assertIsNone(record.call_args.kwargs["speaker"])
            record.assert_called_once()
            log.assert_called_once()

    def test_cancellation_model_rejects_non_cancelled_or_invalid_metadata(self):
        with self.assertRaises(ValueError):
            retry_cancellation.RetryCancellationResult(ExecutionResult("Done", Outcome.CONFIRMED), {"session_id": "session"})
        with self.assertRaises(ValueError):
            retry_cancellation.RetryCancellationResult(ExecutionResult("", Outcome.CANCELLED), {})

    def dispatch_arguments(self):
        return dict(roast_target=Mock(return_value=None), respond_to_roast=Mock(),
                    guest_mode=Mock(), visitors_present=Mock(), response_guest_mode=Mock(),
                    roast_respond=Mock(), assignment_action=Mock(return_value=None), guest_commands={},
                    guest_assignment=Mock(), connection=Mock(return_value="ha"))

    def test_roast_precedence_preserves_typed_identity_without_guest_connection(self):
        arguments = self.dispatch_arguments()
        arguments["roast_target"].return_value = "edd"
        expected = ExecutionResult("Try harder", Outcome.CONFIRMED)
        arguments["respond_to_roast"].return_value = expected
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy conversion")):
            result = roast_guest_dispatch.dispatch_roast_or_guest_result("roast", **arguments)
        self.assertIs(result, expected)
        arguments["assignment_action"].assert_not_called()
        arguments["connection"].assert_not_called()
        arguments["respond_to_roast"].assert_called_once()

    def test_guest_failure_retains_action_evidence_and_owns_request(self):
        arguments = self.dispatch_arguments()
        arguments["assignment_action"].return_value = "clear"
        expected = ExecutionResult("Cannot verify", Outcome.UNVERIFIED, (
            ActionResult(0, "input_text.guests", "input_text.set_value", ActionStatus.UNVERIFIED),))
        arguments["guest_assignment"].return_value = expected
        result = roast_guest_dispatch.dispatch_roast_or_guest_result("clear", **arguments)
        self.assertIs(result, expected)
        arguments["guest_assignment"].assert_called_once_with("clear", "ha")
        arguments["connection"].assert_called_once()
        arguments["respond_to_roast"].assert_not_called()

    def test_guest_legacy_results_are_validated_and_unmatched_does_not_connect(self):
        arguments = self.dispatch_arguments()
        self.assertIsNone(roast_guest_dispatch.dispatch_roast_or_guest_result("hello", **arguments))
        arguments["connection"].assert_not_called()
        arguments["assignment_action"].return_value = "check"
        arguments["guest_assignment"].return_value = ("Done", "confirmed")
        self.assertIs(roast_guest_dispatch.dispatch_roast_or_guest_result("guests", **arguments).outcome, Outcome.CONFIRMED)
        for malformed in (("Done", "invalid"), None, ("Done",)):
            arguments["guest_assignment"].return_value = malformed
            with self.assertRaises(ValueError):
                roast_guest_dispatch.dispatch_roast_or_guest_result("guests", **arguments)

    def test_roast_provider_uses_guest_policy_without_legacy_wrapper(self):
        respond = Mock(return_value="Try harder")
        with patch.object(roast_command_dispatch, "respond_to_roast", side_effect=AssertionError("legacy roast")):
            result = roast_command_dispatch.respond_to_roast_result(
                "edd", guest_mode=lambda: "off", visitors_present=lambda: True,
                response_guest_mode=lambda *_: "on", respond=respond)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        respond.assert_called_once_with("edd", guest=True)


if __name__ == "__main__":
    unittest.main()
