"""Lighting command dispatch regression tests."""
import unittest
from unittest.mock import Mock
from lighting_command_dispatch import dispatch_lighting


class LightingCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "lighting result"
        self.factory = Mock(return_value=self.registry)
        self.context = Mock(return_value="context")
        self.matches = Mock()
        self.parse_light_command = Mock()
        self.handle_light_request = Mock()
        self.action_results = []
        self.last_lights = ["light.kitchen"]

    def dispatch(self, phrase="turn on kitchen lights", source="assist",
                 origin="kitchen", satellite="satellite.kitchen"):
        return dispatch_lighting(phrase, source=source, origin_device=origin,
            satellite=satellite, registry_factory=self.factory,
            context_factory=self.context, matches=self.matches,
            parse_light_command=self.parse_light_command,
            handle_light_request=self.handle_light_request,
            action_results=self.action_results, last_lights=self.last_lights)

    def test_result_returned(self):
        self.assertEqual(self.dispatch(), "lighting result")

    def test_registry_dependencies(self):
        self.dispatch()
        self.factory.assert_called_once_with(matches=self.matches,
            parse_light_command=self.parse_light_command,
            handle_light_request=self.handle_light_request,
            action_results=self.action_results, last_lights=self.last_lights,
            origin_device="kitchen")

    def test_request_context(self):
        self.dispatch()
        self.context.assert_called_once_with(phrase="turn on kitchen lights",
            source="assist", origin_device="kitchen", satellite="satellite.kitchen")

    def test_registry_receives_context(self):
        self.dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_no_match_preserved(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.dispatch())

    def test_browser_source_preserved(self):
        self.dispatch(source="browser")
        self.assertEqual(self.context.call_args.kwargs["source"], "browser")

    def test_missing_origin_preserved(self):
        self.dispatch(origin=None, satellite=None)
        self.assertIsNone(self.context.call_args.kwargs["origin_device"])
        self.assertIsNone(self.context.call_args.kwargs["satellite"])

    def test_actions_list_passed_by_reference(self):
        self.dispatch()
        self.assertIs(self.factory.call_args.kwargs["action_results"], self.action_results)

    def test_last_lights_passed_by_reference(self):
        self.dispatch()
        self.assertIs(self.factory.call_args.kwargs["last_lights"], self.last_lights)
