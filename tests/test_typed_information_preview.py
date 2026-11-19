"""Typed information/preview providers retain legacy APIs and dispatch semantics."""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from declan.turn import command_registry
import conditions
from declan.turn import routine_preview_dispatch
import server
from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
from declan.turn.information_result import InformationResult, InformationCategory


class TypedInformationPreviewTests(unittest.TestCase):
    def test_information_handle_consumes_typed_home_and_forecast_without_legacy_calls(self):
        home = ExecutionResult("Cannot verify", Outcome.UNAVAILABLE)
        forecast = InformationResult(home, InformationCategory.WEATHER)
        with patch.object(conditions, "home_temperatures", side_effect=AssertionError("legacy home")), \
             patch.object(conditions, "home_temperatures_result", return_value=home) as read_home, \
             patch.object(conditions, "forecast_reply", side_effect=AssertionError("legacy forecast")), \
             patch.object(conditions, "forecast_reply_result", return_value=forecast) as read_forecast:
            result = conditions.handle_result("what's the weather", None)
            self.assertIs(result.result, home)
            self.assertIs(conditions.handle_result("weather forecast tomorrow", None), forecast)
        read_home.assert_called_once()
        read_forecast.assert_called_once()
        self.assertIsNone(conditions.handle_result("hello", None))

    def test_information_registry_preserves_action_evidence_and_category_decoration(self):
        action = ActionResult(0, "sensor.temperature", "sensor.read", ActionStatus.CONFIRMED)
        typed = InformationResult(ExecutionResult("Warm", Outcome.CONFIRMED, (action,)), InformationCategory.WEATHER)
        decorate = Mock(return_value="Warm. Sass.")
        handler = command_registry.information_registry(
            matches=lambda *_: True, follow_up=lambda *_: ("weather", None),
            handle=Mock(return_value=typed), question_context=lambda _: "context",
            opener=None, last_information=None, decorate=decorate, guest_mode=lambda: "off")
        result = handler.dispatch(command_registry.RequestContext("weather", "assist"))
        self.assertEqual(result.result.actions, (action,))
        self.assertEqual(result.result.reply, "Warm. Sass.")
        self.assertEqual(result.information_context, "context")
        decorate.assert_called_once_with("Warm", "weather", "off")

    def test_information_model_validates_outcome_and_category_and_preserves_legacy_strings(self):
        result = InformationResult(ExecutionResult("Warm", Outcome.PARTIAL), InformationCategory.WEATHER)
        self.assertEqual(result.as_legacy_triple(), ("Warm", "partial", "weather"))
        self.assertIs(type(result.as_legacy_triple()[1]), str)
        self.assertIs(type(result.as_legacy_triple()[2]), str)
        with self.assertRaises(FrozenInstanceError):
            setattr(result, 'category', InformationCategory.TIME)
        for value in (("Warm", "invalid", "weather"), ("Warm", "confirmed", "invalid"), ("Warm",)):
            with self.assertRaises(ValueError):
                InformationResult.coerce(value)

    def test_preview_core_bypasses_legacy_and_cannot_execute(self):
        selection = (("auto:script.tea", {"mode": "quiet"}), None)
        with patch.object(server, 'select_routine_turn_result', return_value=selection), \
             patch.object(server, "preview_routine", side_effect=AssertionError("legacy preview")), \
             patch.object(server, "execute_routine_result", side_effect=AssertionError("execution")):
            result = server.preview_routine_result("preview tea", "kitchen")
        self.assertIs(result.outcome, Outcome.PREVIEW)
        self.assertIn("Nothing has been run", result.reply)
        self.assertIn("mode=quiet", result.reply)
        with patch.object(server, "preview_routine_result", return_value=result):
            self.assertEqual(server.preview_routine("preview tea"), result.as_legacy_pair())

    def test_preview_dispatch_preserves_typed_identity_origin_and_unmatched(self):
        expected = ExecutionResult("Preview", Outcome.PREVIEW)
        detect = Mock(return_value="tea")
        preview = Mock(return_value=expected)
        arguments = dict(origin_device="kitchen", satellite="study", detect_phrase=detect, preview_routine=preview)
        self.assertIs(routine_preview_dispatch.dispatch_preview_result("preview tea", **arguments), expected)
        preview.assert_called_once_with("tea", "kitchen")
        preview.return_value = ("Preview", "invalid")
        with self.assertRaises(ValueError):
            routine_preview_dispatch.dispatch_preview_result("preview tea", **arguments)
        detect.return_value = None
        preview.reset_mock()
        self.assertIsNone(routine_preview_dispatch.dispatch_preview_result("hello", **arguments))
        preview.assert_not_called()

    def test_legacy_information_handle_retains_triple_and_none(self):
        expected = InformationResult(ExecutionResult("Warm", Outcome.CONFIRMED), InformationCategory.WEATHER)
        with patch.object(conditions, "handle_result", return_value=expected):
            self.assertEqual(conditions.handle("weather", None), ("Warm", "confirmed", "weather"))
        with patch.object(conditions, "handle_result", return_value=None):
            self.assertIsNone(conditions.handle("hello", None))


if __name__ == "__main__":
    unittest.main()
