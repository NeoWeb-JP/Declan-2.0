"""Registry routine path consumes discovered script typed outcomes directly."""
import unittest
from unittest.mock import patch

import server
from execution_results import ExecutionResult, Outcome


class TypedDiscoveredRoutineCoreTests(unittest.TestCase):
    def test_foreground_does_not_use_legacy_routine_wrapper(self):
        typed = ExecutionResult("Routine finished", Outcome.EXECUTION_COMPLETED)
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
                server, "execute_routine", side_effect=AssertionError("legacy wrapper called")), patch.object(
                server.script_discovery, "execute_result", return_value=(typed, "Verified")) as execute:
            self.assertEqual(
                server.execute_routine_result(("auto:script.good_morning", {}), []),
                (typed, "Verified"))
        execute.assert_called_once()

    def test_background_does_not_use_legacy_routine_wrapper(self):
        typed = ExecutionResult("Routine requested", Outcome.STARTED)
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
                server, "execute_routine", side_effect=AssertionError("legacy wrapper called")), patch.object(
                server.script_discovery, "enqueue_result", return_value=(typed, "Job 123")) as enqueue:
            self.assertEqual(
                server.execute_routine_result(("auto:script.good_night", {
                    "_declan_background": True}), []), (typed, "Job 123"))
        enqueue.assert_called_once()

    def test_legacy_non_discovered_selection_still_supported(self):
        with patch.object(server, "execute_routine",
                          side_effect=AssertionError("legacy wrapper called")):
            typed, status = server.execute_routine_result(("unconfigured_house_status", {}), [])
        self.assertIs(typed.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(status)


if __name__ == "__main__":
    unittest.main()
