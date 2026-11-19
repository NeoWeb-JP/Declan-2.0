"""Regression tests for extracted HA routine execution and completion."""
import unittest
from unittest.mock import patch, Mock

import server
import routine_execution_dispatch as dispatch
from execution_results import Outcome


class RoutineExecutionExtractionTests(unittest.TestCase):
    def test_execution_wrapper_preserves_patch_points(self):
        with patch.object(dispatch, "run_routine_result", return_value="sentinel") as helper:
            self.assertEqual(server.run_routine_result("morning"), "sentinel")
        kwargs = helper.call_args.kwargs
        self.assertIs(kwargs["gates"], server.ROUTINE_EXECUTION_GATES)
        self.assertIs(kwargs["cooldown"], server.ROUTINE_COOLDOWN)
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["registry"], server.routine_registry)
        self.assertIs(kwargs["completion"], server.routine_completion_result)
        self.assertIs(kwargs["launch_app"], server.launch_movie_app_result)
        self.assertIs(kwargs["tracker"], server.track_routine)
        self.assertIs(kwargs["request_factory"], server.Request)

    def test_completion_wrapper_preserves_patch_points(self):
        with patch.object(dispatch, "routine_completion_result", return_value="sentinel") as helper:
            self.assertEqual(server.routine_completion_result({}, "id", "script.test", "night", None, None), "sentinel")
        self.assertIs(helper.call_args.kwargs["parse_steps"], server.routine_action_results_typed)
        self.assertIs(helper.call_args.kwargs["extend_evidence"], server.extend_action_evidence)
        self.assertIs(helper.call_args.kwargs["sass"], server.add_sass)

    def test_unconfigured_ha_prevents_dispatch(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            result, detail = server.run_routine_result("morning")
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(detail)

    def test_completion_rejects_uncorrelated_result(self):
        result, detail = server.routine_completion_result(
            {"schema_version": 1, "request_id": "wrong"}, "expected", "script.test", "night", None, None
        )
        self.assertEqual(result.outcome, Outcome.UNVERIFIED)
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
