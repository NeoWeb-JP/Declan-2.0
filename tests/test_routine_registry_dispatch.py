"""Routine registry dispatch context regression tests."""
import unittest
from unittest.mock import Mock
from routine_registry_dispatch import dispatch_routine


class RoutineRegistryDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "handled"
        self.factory = Mock(return_value=self.registry)
        self.context = Mock(return_value="context")
        self.actions = []
        self.select = Mock()
        self.execute = Mock()
        self.args = dict(source="assist", origin_device="bedroom", satellite="kitchen",
                         action_results=self.actions, registry_factory=self.factory,
                         context_factory=self.context, select=self.select,
                         execute=self.execute)

    def run_dispatch(self, **kwargs):
        return dispatch_routine("good night", **(self.args | kwargs))

    def test_dispatch_result(self):
        self.assertEqual(self.run_dispatch(), "handled")

    def test_registry_created_once(self):
        self.run_dispatch()
        self.factory.assert_called_once()

    def test_origin_device_preferred(self):
        self.run_dispatch()
        self.assertEqual(self.factory.call_args.kwargs["origin"], "bedroom")

    def test_satellite_fallback(self):
        self.run_dispatch(origin_device=None)
        self.assertEqual(self.factory.call_args.kwargs["origin"], "kitchen")

    def test_empty_origin_fallback(self):
        self.run_dispatch(origin_device="")
        self.assertEqual(self.factory.call_args.kwargs["origin"], "kitchen")

    def test_raw_origin_preserved_in_context(self):
        self.run_dispatch(origin_device=None)
        self.assertIsNone(self.context.call_args.kwargs["origin_device"])

    def test_context_has_phrase(self):
        self.run_dispatch()
        self.assertEqual(self.context.call_args.kwargs["phrase"], "good night")

    def test_context_has_source(self):
        self.run_dispatch()
        self.assertEqual(self.context.call_args.kwargs["source"], "assist")

    def test_actions_same_reference(self):
        self.run_dispatch()
        self.assertIs(self.factory.call_args.kwargs["action_results"], self.actions)

    def test_select_and_execute_forwarded(self):
        self.run_dispatch()
        self.assertIs(self.factory.call_args.kwargs["select"], self.select)
        self.assertIs(self.factory.call_args.kwargs["execute"], self.execute)

    def test_context_passed_to_dispatch(self):
        self.run_dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_no_match_propagates(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.run_dispatch())

    def test_exception_propagates(self):
        self.registry.dispatch.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            self.run_dispatch()
