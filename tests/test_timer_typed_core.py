"""Timer core returns typed outcomes while legacy handle API remains unchanged."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from declan.timers import timers
from declan.core.execution_results import ExecutionResult, Outcome
from result_pairs import pair, pair_of


class TimerCoreTypedTests(unittest.TestCase):
    def test_timer_lifecycle_constructs_results_with_enum_outcomes(self):
        with TemporaryDirectory() as folder, \
             patch.object(timers, "DATABASE", Path(folder) / "timers.db"), \
             patch.object(timers, "time", return_value=100) as clock, \
             patch.object(timers, "resolve_output", return_value=("assist_satellite.kitchen", "kitchen")), \
             patch.object(timers, "ExecutionResult", wraps=ExecutionResult) as model:
            for phrase, expected in (("set tea timer for 5 minutes", Outcome.TIMER_SET),
                    ("set tea timer for 5 minutes", Outcome.UNRESOLVED),
                    ("list timers", Outcome.TIMER_STATUS),
                    ("increase tea timer by 1 minute", Outcome.TIMER_ADJUSTED),
                    ("stop tea timer", Outcome.UNRESOLVED),
                    ("cancel tea timer", Outcome.TIMER_CANCELLED),
                    ("list timers", Outcome.NO_TIMER),
                    ("set tea timer for 1 second", Outcome.TIMER_SET)):
                with self.subTest(phrase=phrase):
                    result = timers.handle_result(phrase, Mock())
                    self.assertIs(result.outcome, expected)
                    self.assertIs(model.call_args.args[1], expected)
            clock.return_value = 200
            self.assertIs(timers.handle_result("cancel tea timer", Mock()).outcome, Outcome.UNRESOLVED)
            self.assertIs(timers.handle_result("stop tea timer", Mock()).outcome, Outcome.TIMER_STOPPED)
            self.assertTrue(all(isinstance(call.args[1], Outcome) for call in model.call_args_list))

    def test_unmatched_phrase_remains_none(self):
        self.assertIsNone(timers.handle_result("turn on kitchen", Mock()))
        self.assertIsNone(pair_of(timers.handle_result)("turn on kitchen", Mock()))

    def test_invalid_duration_returns_typed_unresolved(self):
        result = timers.handle_result("set a timer for nonsense minutes", Mock())
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        self.assertEqual(pair_of(timers.handle_result)("set a timer for nonsense minutes", Mock()),
                         pair(result))

    def test_missing_alarm_output_is_typed_unavailable(self):
        with patch.object(timers, "resolve_output", return_value=None):
            result = timers.handle_result("set a timer for 5 minutes", Mock())
        self.assertIs(result.outcome, Outcome.UNAVAILABLE)

    def test_no_timer_is_typed(self):
        with patch.object(timers, "database") as database, \
             patch.object(timers, "time", return_value=100):
            db = database.return_value.__enter__.return_value
            db.execute.return_value.fetchall.return_value = []
            result = timers.handle_result("list timers", Mock())
        self.assertIs(result.outcome, Outcome.NO_TIMER)
        self.assertEqual(result.reply, "There are no timers.")

    def test_named_missing_timer_is_typed(self):
        with patch.object(timers, "database") as database, \
             patch.object(timers, "time", return_value=100):
            db = database.return_value.__enter__.return_value
            db.execute.return_value.fetchall.return_value = []
            result = timers.handle_result("cancel kitchen timer", Mock())
        self.assertIs(result.outcome, Outcome.NO_TIMER)
        self.assertIn("couldn't find", result.reply)

    def test_public_handle_uses_typed_core(self):
        with patch.object(timers, "handle_result",
                          return_value=ExecutionResult("Set timer", Outcome.TIMER_SET)):
            self.assertEqual(pair_of(timers.handle_result)("set a timer for 5 minutes", Mock()),
                             ("Set timer", "timer_set"))

    def test_invalid_core_result_cannot_be_silently_accepted(self):
        with patch.object(timers, "handle_result", return_value=("Set", "timer_set")):
            with self.assertRaises(TypeError):
                pair_of(timers.handle_result)("set a timer for 5 minutes", Mock())


if __name__ == "__main__":
    unittest.main()
