"""Typed lighting intent provider and backwards-compatible responses."""
import unittest
from unittest.mock import Mock, patch

from declan.ha import lighting_intents
from declan.core.execution_results import ExecutionResult, Outcome


class LightingTypedCoreTests(unittest.TestCase):
    def test_local_validation_constructs_enum_result_without_legacy_adapter(self):
        with patch.object(lighting_intents, "_lighting_result", side_effect=AssertionError("legacy pair")), \
             patch.object(lighting_intents, "ExecutionResult", wraps=ExecutionResult) as model:
            result = lighting_intents.handle_light_request_result(
                "set kitchen lights to 101 percent", parse_light_command=Mock(), set_lights=Mock())
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        self.assertIs(model.call_args.args[1], Outcome.UNRESOLVED)

    def test_unmatched_phrase_returns_none(self):
        parser = Mock(return_value=None)
        self.assertIsNone(lighting_intents.handle_light_request_result(
            "tell me a joke", parse_light_command=parser, set_lights=Mock()))

    def test_missing_origin_is_typed_unresolved(self):
        parser = Mock(return_value=("kitchen lights", "on"))
        result = lighting_intents.handle_light_request_result(
            "turn the kitchen lights on in here", parse_light_command=parser,
            set_lights=Mock(), origin_device=None)
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.UNRESOLVED)

    def test_brightness_validation_is_typed(self):
        result = lighting_intents.handle_light_request_result(
            "set kitchen lights to 101 percent", parse_light_command=Mock(),
            set_lights=Mock())
        self.assertIs(result.outcome, Outcome.UNRESOLVED)

    def test_action_tuple_is_converted_to_typed_result(self):
        set_lights = Mock(return_value=("Kitchen lights on", "confirmed"))
        parser = Mock(return_value=("kitchen lights", "on"))
        result = lighting_intents.handle_light_request_result(
            "turn kitchen lights on", parse_light_command=parser,
            set_lights=set_lights)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.reply, "Kitchen lights on")

    def test_legacy_api_preserves_pair(self):
        set_lights = Mock(return_value=ExecutionResult("Lights off", Outcome.CONFIRMED))
        parser = Mock(return_value=("kitchen lights", "off"))
        result = lighting_intents.handle_light_request_result(
            "turn kitchen lights off", parse_light_command=parser,
            set_lights=set_lights)
        self.assertEqual((result.reply, result.outcome), ("Lights off", Outcome.CONFIRMED))

    def test_invalid_action_outcome_rejected(self):
        parser = Mock(return_value=("kitchen lights", "on"))
        with self.assertRaises(ValueError):
            lighting_intents.handle_light_request_result(
                "turn kitchen lights on", parse_light_command=parser,
                set_lights=Mock(return_value=("Done", "invented_outcome")))


if __name__ == "__main__":
    unittest.main()
