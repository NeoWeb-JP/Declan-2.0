"""Typed outcome adapters must reject hostile legacy subclasses."""
import unittest

from execution_results import (
    ActionStatus, DispatchResult, ExecutionResult, MovieLaunchResult,
    MovieLaunchStatus, Outcome, parse_outcome,
)
from information_result import InformationResult
from local_outcome_contracts import routine_execution_result, timer_execution_result
from music_provider_result import music_execution_result


class TypedBoundaryTests(unittest.TestCase):
    def test_ordinary_legacy_pairs_remain_supported(self):
        self.assertEqual(timer_execution_result(("Done", "confirmed")).outcome, Outcome.CONFIRMED)
        self.assertEqual(music_execution_result(["Playing", "confirmed"]).reply, "Playing")
        result, status = routine_execution_result(("Done", "confirmed", "ok"))
        self.assertEqual((result.outcome, status), (Outcome.CONFIRMED, "ok"))
        self.assertEqual(InformationResult.coerce(("Now", "confirmed", "time")).result.reply, "Now")
        self.assertEqual(DispatchResult.coerce(("confirmed", "ok")).status, ActionStatus.CONFIRMED)
        self.assertEqual(parse_outcome("confirmed"), Outcome.CONFIRMED)

    def test_hostile_sequence_subclasses_never_iterated(self):
        class HostileTuple(tuple):
            def __len__(self):
                raise RuntimeError("untrusted length")
        class HostileList(list):
            def __len__(self):
                raise RuntimeError("untrusted length")
        for value in (HostileTuple(("Done", "confirmed")),
                      HostileList(["Done", "confirmed"])):
            with self.subTest(kind=type(value).__name__):
                for adapter in (timer_execution_result, music_execution_result,
                                routine_execution_result, InformationResult.coerce,
                                DispatchResult.coerce):
                    with self.assertRaises(ValueError):
                        adapter(value)

    def test_hostile_text_subclasses_are_rejected(self):
        class HostileText(str):
            def __str__(self):
                raise RuntimeError("untrusted string")
        self.assertIsNone(parse_outcome(HostileText("confirmed")))
        with self.assertRaises(ValueError):
            ExecutionResult(HostileText("Done"), Outcome.CONFIRMED)
        with self.assertRaises(ValueError):
            DispatchResult(ActionStatus.CONFIRMED, HostileText("Done"))
        with self.assertRaises(ValueError):
            MovieLaunchResult(MovieLaunchStatus.SENT, HostileText("Done"))
        with self.assertRaises(ValueError):
            routine_execution_result(("Done", "confirmed", HostileText("ok")))


if __name__ == "__main__":
    unittest.main()
