"""Turn context preparation regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.turn_context_preparation import prepare_turn_context


class TurnContextPreparationTests(unittest.TestCase):
    def setUp(self):
        self.suggest = Mock(return_value="try kitchen")
        self.previous = object()
        self.steps = [{"action": "turn_on"}, {"action": "turn_off"}, {"status": "failed"}]

    def prepare(self, steps=None, **overrides):
        args = dict(action_results=self.steps if steps is None else steps,
                    light_result=("ok", "confirmed"), outcome="confirmed",
                    scope="kitchen", message="lights on", now=42.5,
                    suggestion_factory=self.suggest)
        args.update(overrides)
        return prepare_turn_context(self.previous, **args)

    def test_unique_actions_returned(self):
        self.assertEqual(self.prepare()[0], {"turn_on", "turn_off"})

    def test_missing_actions_ignored(self):
        self.assertEqual(self.prepare(steps=[{"status": "confirmed"}])[0], set())

    def test_duplicate_actions_deduplicated(self):
        self.assertEqual(self.prepare(steps=[{"action": "on"}, {"action": "on"}])[0], {"on"})

    def test_empty_steps(self):
        self.assertEqual(self.prepare(steps=[])[0], set())

    def test_suggestion_returned(self):
        self.assertEqual(self.prepare()[1], "try kitchen")

    def test_previous_context_forwarded(self):
        self.prepare()
        self.assertIs(self.suggest.call_args.args[0], self.previous)

    def test_action_set_forwarded(self):
        actions, _ = self.prepare()
        self.assertEqual(self.suggest.call_args.kwargs["actions"], actions)

    def test_light_result_forwarded(self):
        self.prepare()
        self.assertEqual(self.suggest.call_args.kwargs["light_result"], ("ok", "confirmed"))

    def test_outcome_and_scope_forwarded(self):
        self.prepare()
        self.assertEqual(self.suggest.call_args.kwargs["outcome"], "confirmed")
        self.assertEqual(self.suggest.call_args.kwargs["scope"], "kitchen")

    def test_message_and_time_forwarded(self):
        self.prepare()
        self.assertEqual(self.suggest.call_args.kwargs["message"], "lights on")
        self.assertEqual(self.suggest.call_args.kwargs["now"], 42.5)

    def test_no_suggestion_preserved(self):
        self.suggest.return_value = None
        self.assertIsNone(self.prepare()[1])
