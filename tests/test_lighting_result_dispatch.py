"""Lighting dispatch orchestration regression tests."""
from typing import Any
import unittest
from unittest.mock import Mock
from lighting_result_dispatch import dispatch_lighting_result


class LightingResultDispatchTests(unittest.TestCase):
    def setUp(self):
        self.dispatched = Mock()
        self.dispatched.result.as_legacy_pair.return_value = ("Lights on", "confirmed")
        self.dispatch = Mock(return_value=self.dispatched)
        self.context = Mock(return_value=("light.kitchen",))
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.args = dict(source="assist", origin_device="kitchen", satellite=None,
                         registry_factory=Mock(), context_factory=Mock(),
                         matches=Mock(), parse_light_command=Mock(),
                         handle_light_request=Mock(), action_results=self.actions,
                         last_lights=Mock(), scope="kitchen",
                         dispatch_lighting=self.dispatch,
                         confirmed_lighting_context=self.context)

    def run_dispatch(self):
        return dispatch_lighting_result("turn lights on", **self.args)

    def test_success(self):
        self.assertEqual(self.run_dispatch(), ("Lights on", "confirmed", ("light.kitchen",)))

    def test_unhandled(self):
        self.dispatch.return_value = None
        self.assertIsNone(self.run_dispatch())

    def test_unhandled_skips_context(self):
        self.dispatch.return_value = None
        self.run_dispatch()
        self.context.assert_not_called()

    def test_empty_result(self):
        self.dispatched.result.as_legacy_pair.return_value = ()
        self.assertIsNone(self.run_dispatch())

    def test_empty_result_skips_context(self):
        self.dispatched.result.as_legacy_pair.return_value = ()
        self.run_dispatch()
        self.context.assert_not_called()

    def test_failed_result_preserved(self):
        self.dispatched.result.as_legacy_pair.return_value = ("Unavailable", "failed")
        self.assertEqual(self.run_dispatch()[1], "failed")

    def test_context_receives_outcome(self):
        self.run_dispatch()
        self.context.assert_called_once_with("turn lights on", "confirmed", "kitchen", self.actions)

    def test_dispatch_receives_phrase(self):
        self.run_dispatch()
        self.assertEqual(self.dispatch.call_args.args, ("turn lights on",))

    def test_dispatch_receives_origin(self):
        self.run_dispatch()
        self.assertEqual(self.dispatch.call_args.kwargs["origin_device"], "kitchen")

    def test_actions_same_reference(self):
        self.run_dispatch()
        self.assertIs(self.dispatch.call_args.kwargs["action_results"], self.actions)

    def test_result_conversion_once(self):
        self.run_dispatch()
        self.dispatched.result.as_legacy_pair.assert_called_once_with()

    def test_dispatch_error_propagates(self):
        self.dispatch.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            self.run_dispatch()

    def test_context_error_propagates(self):
        self.context.side_effect = ValueError("failed")
        with self.assertRaises(ValueError):
            self.run_dispatch()
