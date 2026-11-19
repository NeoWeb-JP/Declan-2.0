"""Timer command dispatch and preview precedence tests."""
import unittest
from unittest.mock import Mock
from declan.timers.timer_command_dispatch import dispatch_timer


class TimerCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "timer result"
        self.factory = Mock(return_value=self.registry)
        self.context = Mock(return_value="context")
        self.matches = Mock()
        self.handle = Mock()
        self.opener = object()
        self.guest_mode = Mock()
        self.decorate = Mock()

    def dispatch(self, preview=None, phrase="set a timer", source="assist",
                 origin="kitchen", satellite="satellite.kitchen"):
        return dispatch_timer(phrase, source=source, origin_device=origin,
            satellite=satellite, routine_preview=preview,
            registry_factory=self.factory, context_factory=self.context,
            matches=self.matches, handle=self.handle, opener=self.opener,
            guest_mode=self.guest_mode, decorate=self.decorate)

    def test_timer_dispatch_result_returned(self):
        self.assertEqual(self.dispatch(), "timer result")

    def test_routine_preview_prevents_registry_creation(self):
        self.assertIsNone(self.dispatch(preview=("previewed", "confirmed")))
        self.factory.assert_not_called()

    def test_routine_preview_prevents_context_creation(self):
        self.dispatch(preview=("previewed", "confirmed"))
        self.context.assert_not_called()

    def test_timer_registry_dependencies_preserved(self):
        self.dispatch()
        self.factory.assert_called_once_with(matches=self.matches, handle=self.handle,
            opener=self.opener, guest_mode=self.guest_mode, decorate=self.decorate)

    def test_context_contains_origin_and_satellite(self):
        self.dispatch()
        self.context.assert_called_once_with(phrase="set a timer", source="assist",
            origin_device="kitchen", satellite="satellite.kitchen")

    def test_dispatch_receives_constructed_context(self):
        self.dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_browser_source_preserved(self):
        self.dispatch(source="browser")
        self.assertEqual(self.context.call_args.kwargs["source"], "browser")

    def test_missing_origin_preserved(self):
        self.dispatch(origin=None, satellite=None)
        self.assertIsNone(self.context.call_args.kwargs["origin_device"])
        self.assertIsNone(self.context.call_args.kwargs["satellite"])

    def test_none_dispatch_result_preserved(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.dispatch())
