"""Preserve existing Home Assistant routine outcome semantics at typed boundaries."""
import unittest

from declan.core.execution_results import ExecutionResult, Outcome
from declan.core.local_outcome_contracts import routine_execution_result


class RoutineOutcomeCompatibilityTests(unittest.TestCase):
    def test_existing_routine_outcomes_are_typed(self):
        cases = {
            "reported_success": Outcome.REPORTED_SUCCESS,
            "execution_completed": Outcome.EXECUTION_COMPLETED,
            "cancelled": Outcome.CANCELLED,
            "rejected": Outcome.REJECTED,
            "duplicate": Outcome.DUPLICATE,
        }
        for legacy, expected in cases.items():
            with self.subTest(outcome=legacy):
                result, status = routine_execution_result(("Routine response", legacy, None))
                self.assertIs(result.outcome, expected)
                self.assertEqual(result.as_legacy_pair(), ("Routine response", legacy))
                self.assertIsNone(status)

    def test_status_message_is_preserved(self):
        result, status = routine_execution_result(
            ("Routine completed", "reported_success", "Lights verified"))
        self.assertIs(result.outcome, Outcome.REPORTED_SUCCESS)
        self.assertEqual(status, "Lights verified")

    def test_unknown_outcome_still_rejected(self):
        with self.assertRaises(ValueError):
            routine_execution_result(("Routine response", "unknown_new_status", None))

    def test_other_existing_outcomes_still_work(self):
        for outcome in ("confirmed", "partial", "failed", "unverified", "started"):
            with self.subTest(outcome=outcome):
                result, _ = routine_execution_result(("Routine response", outcome, None))
                self.assertIsInstance(result, ExecutionResult)


if __name__ == "__main__":
    unittest.main()
