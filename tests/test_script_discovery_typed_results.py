"""Typed script discovery results preserve existing HA execution and receipt contracts."""
import unittest
from unittest.mock import patch

import script_discovery
from execution_results import ExecutionResult, Outcome


class ScriptDiscoveryTypedResultTests(unittest.TestCase):
    def test_enqueue_success_preserves_receipt(self):
        with patch.object(script_discovery, "_enqueue_provider", return_value=(
                "Routine requested.", "started", "Background job declan-123")) as enqueue:
            result, detail = script_discovery.enqueue_result(None, "script.morning", {})
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.STARTED)
        self.assertEqual(detail, "Background job declan-123")
        enqueue.assert_called_once_with(None, "script.morning", {})

    def test_enqueue_unverified_preserves_no_receipt(self):
        with patch.object(script_discovery, "_enqueue_provider", return_value=(
                "Home Assistant did not acknowledge.", "unverified", None)):
            result, detail = script_discovery.enqueue_result(None, "script.morning", {})
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.assertIsNone(detail)

    def test_execute_success_preserves_reported_success(self):
        with patch.object(script_discovery, "_execute_provider", return_value=(
                "Routine complete.", "reported_success", None)) as execute:
            result, detail = script_discovery.execute_result(
                None, {"entity_id": "script.morning"}, parameters={"mode": "on"},
                expect_response=True, action_results=[])
        self.assertIs(result.outcome, Outcome.REPORTED_SUCCESS)
        self.assertEqual(result.as_legacy_pair(), ("Routine complete.", "reported_success"))
        self.assertIsNone(detail)
        self.assertEqual(execute.call_count, 1)

    def test_execute_completed_outcome_is_valid(self):
        with patch.object(script_discovery, "_execute_provider", return_value=(
                "Routine finished.", "execution_completed", "verified")):
            result, detail = script_discovery.execute_result(
                None, {"entity_id": "script.morning"})
        self.assertIs(result.outcome, Outcome.EXECUTION_COMPLETED)
        self.assertEqual(detail, "verified")

    def test_invalid_provider_outcome_rejected(self):
        with patch.object(script_discovery, "_execute_provider", return_value=(
                "Unexpected", "not_a_real_outcome", None)):
            with self.assertRaises(ValueError):
                script_discovery.execute_result(None, {"entity_id": "script.morning"})


if __name__ == "__main__":
    unittest.main()
