"""Stop-everywhere registry supports typed and legacy playback cancellation outcomes."""
import unittest

from declan.turn import command_registry
from execution_results import ExecutionResult, Outcome


class StopEverywhereTypedOutcomeTests(unittest.TestCase):
    def _run(self, stop_everywhere):
        registry = command_registry.stop_registry(
            stop_routines=lambda: ("Stopped", "confirmed", None),
            stop_everywhere=stop_everywhere,
            connection=lambda: "connection",
        )
        context = command_registry.RequestContext(
            phrase="stop", source="assist", origin_device=None, satellite=None)
        return registry.dispatch(context)

    def test_legacy_stop_everywhere_triple_is_accepted(self):
        result = self._run(lambda connection: ("", "partial", "One player did not stop"))
        self.assertIs(result.result.outcome, Outcome.PARTIAL)
        self.assertEqual(result.routine_status, "One player did not stop")

    def test_typed_stop_everywhere_result_is_accepted(self):
        typed = ExecutionResult("", Outcome.CONFIRMED)
        result = self._run(lambda connection: (typed, "Playback stopped"))
        self.assertIs(result.result, typed)
        self.assertEqual(result.routine_status, "Playback stopped")

    def test_invalid_stop_everywhere_outcome_is_rejected(self):
        with self.assertRaises(ValueError):
            self._run(lambda connection: ("", "invalid_stop_outcome", None))


if __name__ == "__main__":
    unittest.main()
