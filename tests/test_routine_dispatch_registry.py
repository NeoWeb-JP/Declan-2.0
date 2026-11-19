"""Typed routine command registry tests."""
from typing import Any
from unittest import TestCase
from unittest.mock import Mock
from declan.turn.command_registry import RequestContext, routine_registry
from declan.core.execution_results import Outcome

class RoutineDispatchTests(TestCase):
    def setUp(self):
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.select = Mock(return_value=None)
        self.execute = Mock(return_value=("Routine started.", "confirmed", "Done"))
        self.registry = routine_registry(select=self.select, execute=self.execute,
                                         action_results=self.actions, origin="kitchen")

    def dispatch(self, phrase):
        return self.registry.dispatch(RequestContext(phrase=phrase, source="assist"))

    def test_unmatched_does_not_execute(self):
        self.assertIsNone(self.dispatch("what is the weather"))
        self.execute.assert_not_called()
        self.select.assert_called_once_with("what is the weather", "kitchen")

    def test_executes_selected_script_once(self):
        selection: tuple[Any, ...]
        selection = ("auto:script.declan_good_morning", {})
        self.select.return_value = (selection, None)
        result = self.dispatch("good morning")
        self.execute.assert_called_once_with(selection, self.actions)
        self.assertEqual(result.result.as_legacy_pair(), ("Routine started.", "confirmed"))
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.routine_status, "Done")
        self.assertIsNone(result.routine_follow_on)
        self.assertEqual(result.routine_selection, (selection, None))

    def test_chained_follow_on_preserved(self):
        selection: tuple[Any, ...]
        selection = ("auto:script.declan_movie_time", {})
        self.select.return_value = (selection, "turn off kitchen")
        result = self.dispatch("movie time and turn off kitchen")
        self.assertEqual(result.routine_follow_on, "turn off kitchen")
        self.assertEqual(result.routine_selection, (selection, "turn off kitchen"))
        self.execute.assert_called_once_with(selection, self.actions)

    def test_unconfigured_script_keeps_failure(self):
        self.select.return_value = (("unconfigured_house_status", {}), None)
        self.execute.return_value = ("Script not found.", "not_configured", None)
        result = self.dispatch("house status")
        self.assertIs(result.result.outcome, Outcome.NOT_CONFIGURED)

    def test_unverified_execution_does_not_retry(self):
        self.select.return_value = (("auto:script.test", {}), None)
        self.execute.return_value = ("Couldn't verify execution.", "unverified", None)
        result = self.dispatch("run test")
        self.assertIs(result.result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(self.execute.call_count, 1)
