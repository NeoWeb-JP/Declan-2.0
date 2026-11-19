"""Response orchestration retains typed results until wire/history boundaries."""
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock, patch

from command_response import CommandResponse
from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
import conversation_persistence
import device_result_response
import early_command_result
import information_result_response
import stop_result_response
import turn_finalization


class TypedCommandResponseTests(unittest.TestCase):
    def setUp(self):
        action = ActionResult(0, "light.study", "light.turn_on", ActionStatus.CONFIRMED)
        self.result = ExecutionResult("Done", Outcome.CONFIRMED, (action,))

    def test_response_conversions_preserve_execution_identity_and_context(self):
        context = {"question": "temperature"}
        dispatch = SimpleNamespace(result=self.result, routine_status="Stopped", information_context=context,
                                   status_target="light.study")
        for module, name, field, expected in (
                (stop_result_response, "stop_response", "routine_status", "Stopped"),
                (information_result_response, "information_response", "information_context", context),
                (device_result_response, "device_response", "status_target", "light.study")):
            with self.subTest(response=name), patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy conversion")):
                response = getattr(module, name)(dispatch)
            self.assertIs(response.result, self.result)
            self.assertEqual(getattr(response, field), expected)
            self.assertIs(response.result.actions, self.result.actions)

    def test_response_model_is_frozen_and_validates_result_and_text_fields(self):
        response = CommandResponse(self.result)
        with self.assertRaises(FrozenInstanceError):
            setattr(response, 'status_target', "light.other")
        for arguments in ({"result": ("Done", "confirmed")},
                          {"result": self.result, "routine_status": 1},
                          {"result": self.result, "status_target": []}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                CommandResponse(**arguments)

    def test_preview_priority_does_not_inspect_timer_and_validates_legacy_outcome(self):
        class UnusedTimer:
            @property
            def result(self):
                raise AssertionError("Preview must not inspect timer result")
        timer = UnusedTimer()
        preview = ExecutionResult("Preview", Outcome.PREVIEW)
        self.assertIs(early_command_result.select_early_result(preview, timer), preview)
        self.assertIs(early_command_result.select_early_result(("Preview", "preview"), timer).outcome, Outcome.PREVIEW)
        with self.assertRaises(ValueError):
            early_command_result.select_early_result(("Preview", "invalid"), timer)

    def test_timer_retains_action_evidence_and_rejects_untyped_dispatch(self):
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy conversion")):
            self.assertIs(early_command_result.select_early_result(None, SimpleNamespace(result=self.result)), self.result)
        self.assertIsNone(early_command_result.select_early_result(None, None))
        with self.assertRaises(ValueError):
            early_command_result.select_early_result(None, SimpleNamespace(result=("Done", "confirmed")))

    def test_http_metadata_serializes_enum_to_plain_string(self):
        reply = turn_finalization.apply_outcome_metadata({}, outcome=Outcome.CONFIRMED, routine_status=None)
        self.assertIs(type(reply["outcome"]), str)
        self.assertEqual(reply["outcome"], "confirmed")

    def test_history_boundary_passes_plain_string_and_records_once(self):
        record = Mock()
        reply = {"session_id": "session", "reply": "Done"}
        saved = conversation_persistence.save_turn(
            reply, source="assist", message="lights", outcome=Outcome.CONFIRMED,
            routine_status=None, action_results=[], phrase_suggestion=None,
            speaker=None, record=record, diagnostic_id=lambda: "trace", log_error=Mock())
        self.assertTrue(saved)
        record.assert_called_once()
        self.assertIs(type(record.call_args.args[4]), str)
        self.assertEqual(record.call_args.args[4], "confirmed")


if __name__ == "__main__":
    unittest.main()
