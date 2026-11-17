"""Information registry regression tests for follow-ups and result ownership."""
from unittest import TestCase
from unittest.mock import Mock

import conditions
from command_registry import RequestContext, information_registry
from execution_results import Outcome


class InformationRegistryTests(TestCase):
    def setUp(self):
        self.handle = Mock(return_value=("It's sunny.", "confirmed", "weather"))
        self.decorate = Mock(side_effect=lambda reply, category, guest: reply + " Sass.")
        self.guest = Mock(return_value="off")

    def dispatch(self, phrase, last=None):
        registry = information_registry(matches=conditions.matches, follow_up=conditions.follow_up,
            handle=self.handle, question_context=conditions.question_context, opener="opener",
            last_information=last, decorate=self.decorate, guest_mode=self.guest)
        return registry.dispatch(RequestContext(phrase=phrase, source="assist"))

    def test_direct_weather_query_preserves_context_and_sass(self):
        result = self.dispatch("what's the weather")
        self.assertEqual(result.handler, "information")
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.result.reply, "It's sunny. Sass.")
        self.assertEqual(result.information_context, ("weather", None, None))
        self.handle.assert_called_once_with("what's the weather", "opener")

    def test_contextual_follow_up_resolves_before_execution(self):
        result = self.dispatch("what about tomorrow", ("weather", "oxford", "today"))
        self.assertEqual(result.handler, "information")
        self.handle.assert_called_once_with("what's the weather forecast tomorrow in oxford", "opener")

    def test_follow_up_without_context_requests_clarification(self):
        result = self.dispatch("and tomorrow")
        self.assertIs(result.result.outcome, Outcome.UNRESOLVED)
        self.handle.assert_not_called()
        self.decorate.assert_not_called()

    def test_unavailable_does_not_decorate(self):
        self.handle.return_value = ("Weather unavailable.", "unavailable", "weather")
        result = self.dispatch("what's the weather")
        self.assertIs(result.result.outcome, Outcome.UNAVAILABLE)
        self.assertEqual(result.result.reply, "Weather unavailable.")
        self.decorate.assert_not_called()

    def test_non_information_falls_through_without_side_effects(self):
        self.assertIsNone(self.dispatch("turn on the lights"))
        self.handle.assert_not_called()
        self.guest.assert_not_called()

    def test_time_follow_up_at_home_requires_place_clarification(self):
        result = self.dispatch("what about home", ("time", "oxford", None))
        self.assertIs(result.result.outcome, Outcome.UNRESOLVED)
        self.assertEqual(result.result.reply, "Which place should I check the local time for?")
        self.handle.assert_not_called()
