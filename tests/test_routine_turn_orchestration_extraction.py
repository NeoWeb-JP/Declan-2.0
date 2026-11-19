"""Regression coverage for extracted routine turn orchestration."""
import unittest
from unittest.mock import Mock, patch

import server
import routine_turn_orchestration
from execution_results import Outcome
from routine_selection_results import RoutineSelection, RoutineSelectionKind


class RoutineTurnExtractionTests(unittest.TestCase):
    def test_wrapper_injects_live_selection_and_movie_parser(self):
        with patch.object(routine_turn_orchestration, "select_routine_turn_result", return_value=None) as helper:
            self.assertIsNone(server.select_routine_turn_result("good morning", None))
        self.assertIs(helper.call_args.kwargs["select"], server.select_routine_result)
        self.assertIs(helper.call_args.kwargs["parse_movie"], server.parse_movie_request)

    def test_preview_does_not_dispatch(self):
        with patch.object(server, "select_routine_turn_result", return_value=None):
            with patch.object(server.script_discovery, "execute_result") as dispatch:
                result = server.preview_routine_result("missing")
        self.assertEqual(result.outcome, Outcome.UNRESOLVED)
        dispatch.assert_not_called()

    def test_execution_injects_discovery_and_connection(self):
        with patch.object(routine_turn_orchestration, "execute_routine_result", return_value="sentinel") as helper:
            self.assertEqual(server.execute_routine_result("selection", []), "sentinel")
        self.assertIs(helper.call_args.kwargs["discovery"], server.script_discovery)
        self.assertIs(helper.call_args.kwargs["connect"], server.ha_device_connection)

    def test_missing_selection_never_calls_discovery(self):
        discovery = Mock()
        selection = RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING)
        result, status = routine_turn_orchestration.execute_routine_result(
            selection, [], discovery=discovery, connect=Mock(),
        )
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(status)
        discovery.execute_result.assert_not_called()
        discovery.enqueue_result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
