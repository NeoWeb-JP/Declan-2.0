"""Typed discovered script providers retain the legacy routine execution contract."""
import unittest
from unittest.mock import patch

import server
from declan.core.execution_results import ExecutionResult, Outcome


class TypedScriptDiscoveryDispatchTests(unittest.TestCase):
    def test_discovered_script_execution_preserves_triple(self):
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
                server.script_discovery, "execute_result",
                return_value=(ExecutionResult("Morning complete", Outcome.REPORTED_SUCCESS), None)) as execute:
            result = server.execute_routine(("auto:script.good_morning", {}), [])
        self.assertEqual(result, ("Morning complete", "reported_success", None))
        self.assertEqual(execute.call_count, 1)

    def test_background_receipt_preserved(self):
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
                server.script_discovery, "enqueue_result",
                return_value=(ExecutionResult("Routine requested", Outcome.STARTED),
                              "Background job declan-123")) as enqueue:
            result = server.execute_routine(("auto:script.good_morning", {
                "_declan_background": True, "room": "kitchen"}), [])
        self.assertEqual(result, ("Routine requested", "started", "Background job declan-123"))
        enqueue.assert_called_once_with(None, "script.good_morning", {"room": "kitchen"})

    def test_failed_discovered_script_preserves_outcome(self):
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
                server.script_discovery, "execute_result",
                return_value=(ExecutionResult("Execution not verified", Outcome.UNVERIFIED), None)):
            result = server.execute_routine(("auto:script.good_morning", {}), [])
        self.assertEqual(result, ("Execution not verified", "unverified", None))

    def test_unconfigured_selection_unchanged(self):
        self.assertEqual(server.execute_routine(("unconfigured_house_status", {}), []),
                         ("I could not find a House Status script in Home Assistant.",
                          "not_configured", None))


if __name__ == "__main__":
    unittest.main()
