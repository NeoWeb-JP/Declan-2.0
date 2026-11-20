"""Typed script discovery results preserve existing HA execution and receipt contracts."""
from typing import Any, cast
import unittest
from result_pairs import pair
import json
from unittest.mock import MagicMock, patch

from declan.ha import script_discovery
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha.script_provider_results import BackgroundReceiptResult, BackgroundReceiptStatus


class ScriptDiscoveryTypedResultTests(unittest.TestCase):
    def test_correlated_receipts_are_typed_and_immutable(self):
        payload = {"status": "accepted", "job_id": "declan-fixed", "entity_id": "script.morning"}
        result = BackgroundReceiptResult.parse(202, payload, job_id="declan-fixed", entity_id="script.morning")
        self.assertIs(result.status, BackgroundReceiptStatus.ACCEPTED)
        with self.assertRaises(AttributeError):
            setattr(result, "status", BackgroundReceiptStatus.UNVERIFIED)
        with self.assertRaises(TypeError):
            cast(Any, BackgroundReceiptResult)("accepted")

    def test_real_enqueue_preserves_conservative_receipt_decisions(self):
        cases: list[tuple[int, object, Outcome]]
        valid = {"status": "accepted", "job_id": "declan-fixed", "entity_id": "script.morning"}
        cases = [(202, valid, Outcome.STARTED), (200, valid, Outcome.UNVERIFIED)]
        for key, value in (("status", "ACCEPTED"), ("status", "completed"),
                           ("job_id", "other"), ("entity_id", "script.other"),
                           ("status", []), ("job_id", None)):
            cases.append((202, {**valid, key: value}, Outcome.UNVERIFIED))
        payload: object
        for payload in (None, [], {}, "accepted"):
            cases.append((202, payload, Outcome.UNVERIFIED))
        for status, payload, expected in cases:
            with self.subTest(status=status, payload=payload):
                opener = MagicMock()
                response = opener.open.return_value.__enter__.return_value
                response.status = status
                response.read.return_value = json.dumps(payload).encode()
                with patch.object(script_discovery.secrets, "token_hex", return_value="fixed"):
                    result, detail = script_discovery.enqueue_result(
                        ("http://ha.invalid", {}, opener), "script.morning", {})
                self.assertIs(result.outcome, expected)
                self.assertEqual(detail, "Background job declan-fixed" if expected is Outcome.STARTED else None)
                self.assertEqual(opener.open.call_args.kwargs["timeout"], 2)
                request = opener.open.call_args.args[0]
                self.assertEqual(json.loads(request.data), {"entity_id": "script.morning", "job_id": "declan-fixed", "parameters": {}})

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
        self.assertEqual(pair(result), ("Routine complete.", "reported_success"))
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
