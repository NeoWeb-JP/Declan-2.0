"""Typed routine execution adapter compatibility and validation."""
import unittest

from declan.core.execution_results import ExecutionResult, Outcome
from declan.core.local_outcome_contracts import routine_execution_result


class RoutineExecutionTypedBoundaryTests(unittest.TestCase):
    def test_direct_typed_result_has_no_status(self):
        result = ExecutionResult("Routine started", Outcome.STARTED)
        self.assertEqual(routine_execution_result(result), (result, None))

    def test_typed_result_with_status(self):
        result = ExecutionResult("Routine started", Outcome.STARTED)
        self.assertEqual(routine_execution_result((result, "Starting")),
                         (result, "Starting"))

    def test_legacy_triple_is_accepted(self):
        result, status = routine_execution_result(
            ("Routine completed", "confirmed", "All done"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(status, "All done")

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            routine_execution_result(
                (ExecutionResult("Done", Outcome.CONFIRMED), 123))

    def test_invalid_outcome_is_rejected(self):
        with self.assertRaises(ValueError):
            routine_execution_result(("Done", "invented", None))

    def test_unstructured_result_is_rejected(self):
        with self.assertRaises(ValueError):
            routine_execution_result("Done")


if __name__ == "__main__":
    unittest.main()
