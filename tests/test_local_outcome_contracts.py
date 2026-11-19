"""Timer and routine provider contract regression tests."""
import unittest
from unittest.mock import Mock

from declan.turn.command_registry import RequestContext, routine_registry, timer_registry
from declan.core.execution_results import ExecutionResult, Outcome
from declan.core.local_outcome_contracts import timer_execution_result, routine_execution_result


class LocalProviderContractsTests(unittest.TestCase):
    def test_timer_legacy_outcome_typed(self):
        self.assertIs(timer_execution_result(("Timer set", "timer_set")).outcome, Outcome.TIMER_SET)

    def test_timer_accepts_typed_result_identity(self):
        result = ExecutionResult("Done", Outcome.TIMER_STOPPED)
        self.assertIs(timer_execution_result(result), result)

    def test_timer_invalid_outcome_rejected(self):
        with self.assertRaises(ValueError):
            timer_execution_result(("Done", "unknown"))

    def test_timer_malformed_result_rejected(self):
        for value in (None, (), ("Done",), ("Done", "confirmed", "extra"), "Done"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                timer_execution_result(value)

    def test_routine_legacy_triple_typed(self):
        result, status = routine_execution_result(("Started", "confirmed", "running"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(status, "running")

    def test_routine_accepts_typed_pair(self):
        original = ExecutionResult("Started", Outcome.REQUESTED)
        result, status = routine_execution_result((original, "queued"))
        self.assertIs(result, original)
        self.assertEqual(status, "queued")

    def test_routine_rejects_bad_status(self):
        with self.assertRaises(ValueError):
            routine_execution_result(("Started", "confirmed", 4))

    def test_routine_rejects_invalid_outcome(self):
        with self.assertRaises(ValueError):
            routine_execution_result(("Started", "invalid", None))

    def test_routine_rejects_malformed_result(self):
        for value in (None, (), ("Started",), "Started"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                routine_execution_result(value)

    def test_timer_registry_accepts_typed_provider_and_decorates(self):
        decorate = Mock(return_value="Sassy timer")
        registry = timer_registry(
            matches=lambda _: True,
            handle=lambda *_args, **_kw: ExecutionResult("Set", Outcome.TIMER_SET),
            opener=None, guest_mode=lambda: "off", decorate=decorate,
        )
        result = registry.dispatch(RequestContext("set timer", "assist"))
        self.assertEqual(result.result.as_legacy_pair(), ("Sassy timer", "timer_set"))
        decorate.assert_called_once_with("Set", "timer_set", "off")

    def test_routine_registry_accepts_typed_provider(self):
        original = ExecutionResult("Morning started", Outcome.CONFIRMED)
        registry = routine_registry(
            select=lambda *_: ("morning", None),
            execute=lambda *_: (original, "done"),
            action_results=[], origin="kitchen",
        )
        result = registry.dispatch(RequestContext("good morning", "assist"))
        self.assertIs(result.result, original)
        self.assertEqual(result.routine_status, "done")
        self.assertEqual(result.routine_reply, "Morning started")

    def test_timer_invalid_provider_result_never_falls_through(self):
        registry = timer_registry(
            matches=lambda _: True,
            handle=lambda *_args, **_kw: ("Set", "unknown"),
            opener=None, guest_mode=lambda: "off", decorate=lambda *args: args[0],
        )
        with self.assertRaises(ValueError):
            registry.dispatch(RequestContext("set timer", "assist"))


if __name__ == "__main__":
    unittest.main()
