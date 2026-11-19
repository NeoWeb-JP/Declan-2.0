"""Timer registry recognition, routing and compatibility tests."""
from unittest import TestCase
from unittest.mock import Mock

from declan.timers import timers
from declan.turn.command_registry import RequestContext, timer_registry
from declan.core.execution_results import Outcome


class TimerRegistryTests(TestCase):
    def setUp(self):
        self.handle = Mock(return_value=("Set tea timer.", "timer_set"))
        self.decorate = Mock(side_effect=lambda reply, outcome, guest: reply + " Sass.")
        self.guest = Mock(return_value="off")
        self.registry = timer_registry(matches=timers.matches, handle=self.handle,
            opener="HA", guest_mode=self.guest, decorate=self.decorate)

    def dispatch(self, phrase, **kwargs):
        return self.registry.dispatch(RequestContext(phrase=phrase, source="assist", **kwargs))

    def test_creation_and_legacy_outcome(self):
        result = self.dispatch("set a tea timer for 5 minutes", satellite="kitchen", origin_device="tablet")
        self.assertEqual(result.handler, "timer")
        self.assertIs(result.result.outcome, Outcome.TIMER_SET)
        self.assertEqual(result.result.as_legacy_pair(), ("Set tea timer. Sass.", "timer_set"))
        self.handle.assert_called_once_with("set a tea timer for 5 minutes", "HA",
            satellite="kitchen", device="tablet", browser=False)
        self.decorate.assert_called_once_with("Set tea timer.", "timer_set", "off")

    def test_timer_stop_is_not_whole_house_stop(self):
        self.handle.return_value = ("Cancelled tea.", "timer_cancelled")
        result = self.dispatch("cancel tea timer")
        self.assertEqual(result.handler, "timer")
        self.assertIs(result.result.outcome, Outcome.TIMER_CANCELLED)

    def test_plain_stop_is_not_timer(self):
        self.assertIsNone(self.dispatch("stop"))
        self.handle.assert_not_called()

    def test_invalid_satellite_is_dropped(self):
        self.dispatch("list timers", satellite="x" * 129)
        self.assertIsNone(self.handle.call_args.kwargs["satellite"])

    def test_query_does_not_decorate(self):
        self.handle.return_value = ("No timers.", "no_timer")
        result = self.dispatch("list timers")
        self.assertIs(result.result.outcome, Outcome.NO_TIMER)
        self.decorate.assert_not_called()
        self.guest.assert_not_called()

    def test_unmatched_has_no_side_effects(self):
        self.assertIsNone(self.dispatch("turn on the kitchen light"))
        self.handle.assert_not_called()

    def test_matched_failure_does_not_fall_through(self):
        self.handle.return_value = ("No available satellite.", "unavailable")
        result = self.dispatch("set a timer for 2 minutes")
        self.assertIs(result.result.outcome, Outcome.UNAVAILABLE)
        self.decorate.assert_not_called()
