"""Lighting registry matching and compatibility tests."""
from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from declan.ha import lighting_intents
from declan.turn.command_registry import RequestContext, lighting_registry
from declan.core.execution_results import Outcome


class LightingRegistryTests(TestCase):
    def setUp(self):
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.execute = Mock(return_value=("Kitchen lights on.", "confirmed"))
        self.parse = Mock(side_effect=lambda phrase: ("kitchen", "on") if phrase == "turn on kitchen" else None)
        self.registry = lighting_registry(matches=lighting_intents.matches,
            parse_light_command=self.parse, handle_light_request=self.execute,
            action_results=self.actions, last_lights=("kitchen",), origin_device="kitchen satellite")

    def dispatch(self, phrase):
        return self.registry.dispatch(RequestContext(phrase=phrase, source="assist"))

    def test_explicit_lighting_preserves_action_context(self):
        result = self.dispatch("turn on kitchen")
        self.assertEqual(result.handler, "lighting")
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.result.as_legacy_pair(), ("Kitchen lights on.", "confirmed"))
        self.execute.assert_called_once_with("turn on kitchen", action_results=self.actions,
            last_lights=("kitchen",), origin_device="kitchen satellite")

    def test_contextual_lighting_claims_request(self):
        self.assertEqual(self.dispatch("turn them off").handler, "lighting")
        self.assertEqual(self.dispatch("make it brighter in kitchen").handler, "lighting")

    def test_status_query_claims_request(self):
        self.assertEqual(self.dispatch("what lights are on").handler, "lighting")

    def test_brightness_validation_is_owned_by_lighting(self):
        self.execute.return_value = ("Choose a brightness from 0 to 100 percent.", "unresolved")
        result = self.dispatch("set kitchen to 120 percent")
        self.assertIs(result.result.outcome, Outcome.UNRESOLVED)

    def test_unmatched_phrase_has_no_side_effects(self):
        self.assertIsNone(self.dispatch("what is the weather tomorrow"))
        self.execute.assert_not_called()

    def test_uncertain_execution_does_not_fall_through(self):
        self.execute.return_value = ("Couldn't verify light state.", "unverified")
        result = self.dispatch("turn on kitchen")
        self.assertIs(result.result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(self.execute.call_count, 1)
