"""Routine follow-on accepts both typed and legacy lighting results."""
import unittest
from unittest.mock import Mock

from declan.turn import routine_follow_on
from declan.core.execution_results import ExecutionResult, Outcome


def run_follow_on(lighting_result):
    return routine_follow_on.execute(
        "turn kitchen lights on",
        routine_reply="Routine complete", routine_outcome="confirmed",
        routine_status=None, parse_music=Mock(), play_music=Mock(),
        connection=Mock(), music_inventory=Mock(),
        handle_lighting=Mock(return_value=lighting_result),
        last_lights=(), origin=None, music_origin=None,
        action_results=[], scope=None,
        chained_outcome=lambda routine, lighting: (
            "confirmed" if routine == lighting == "confirmed" else "failed"
        ),
    )


class RoutineFollowOnTypedTests(unittest.TestCase):
    def test_typed_lighting_result_is_accepted(self):
        result = run_follow_on(ExecutionResult("Kitchen on", Outcome.CONFIRMED))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIn("Kitchen on", result.reply)

    def test_legacy_lighting_pair_is_accepted(self):
        result = run_follow_on(("Kitchen on", "confirmed"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)

    def test_missing_lighting_result_is_unresolved(self):
        result = run_follow_on(None)
        self.assertIs(result.outcome, Outcome.FAILED)
        self.assertIn("couldn't understand", result.reply)

    def test_invalid_lighting_outcome_is_rejected(self):
        with self.assertRaises(ValueError):
            run_follow_on(("Kitchen on", "invented_outcome"))


if __name__ == "__main__":
    unittest.main()
