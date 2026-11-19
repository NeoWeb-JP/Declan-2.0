"""Stop routine registry validates typed and legacy cancellation results."""
import unittest

from declan.turn import command_registry
from declan.core.execution_results import ExecutionResult, Outcome


class StopRoutineTypedOutcomeTests(unittest.TestCase):
    def _run(self, stop_routines):
        registry = command_registry.stop_registry(
            stop_routines=stop_routines,
            stop_everywhere=lambda _: ("Stopped", "confirmed", None),
            connection=lambda: None,
        )
        context = command_registry.RequestContext(
            phrase="stop routine", source="assist", origin_device=None, satellite=None)
        return registry.dispatch(context)

    def test_legacy_cancellation_triple_is_accepted(self):
        result = self._run(lambda: ("Cancellation requested", "unverified", "Pending"))
        self.assertIs(result.result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(result.routine_status, "Pending")

    def test_typed_cancellation_result_is_accepted(self):
        typed = ExecutionResult("Cancellation requested", Outcome.UNVERIFIED)
        result = self._run(lambda: (typed, "Pending"))
        self.assertIs(result.result, typed)
        self.assertEqual(result.routine_status, "Pending")

    def test_malformed_cancellation_result_is_rejected(self):
        with self.assertRaises(ValueError):
            self._run(lambda: ("Cancellation requested", "not_a_real_outcome", None))


if __name__ == "__main__":
    unittest.main()
