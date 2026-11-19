"""All internal turn stages preserve enum outcomes before final dispatch."""
import unittest
from dataclasses import FrozenInstanceError

from execution_results import Outcome
from turn_direct_dispatch import DirectDispatchResult
from turn_routine_stage import RoutineStageResult
from turn_fallback_dispatch import FallbackDispatchResult
from turn_response_preparation import PreparedResponse


class TurnStageOutcomeContractTests(unittest.TestCase):
    def stages(self, outcome):
        return (
            lambda: DirectDispatchResult("reply", outcome, "display text"),
            lambda: RoutineStageResult("reply", outcome, "display text", None, None, None),
            lambda: FallbackDispatchResult("reply", outcome),
            lambda: PreparedResponse("reply", outcome, "off", False, "off", None),
        )

    def test_every_stage_normalizes_known_outcomes_and_preserves_none(self):
        for outcome in (*Outcome, None):
            for factory in self.stages(outcome.value if outcome is not None else None):
                with self.subTest(outcome=outcome, stage=factory):
                    self.assertIs(factory().outcome, outcome)

    def test_unknown_or_malformed_outcomes_are_not_carried_to_next_stage(self):
        for outcome in ("ok", "success", "answered", "", "CONFIRMED", True, 1, {}):
            for factory in self.stages(outcome):
                with self.subTest(outcome=outcome, stage=factory), self.assertRaises(ValueError):
                    factory()

    def test_outcome_identity_cannot_be_reassigned(self):
        for factory in self.stages(Outcome.UNVERIFIED):
            result = factory()
            with self.assertRaises(FrozenInstanceError):
                result.outcome = Outcome.CONFIRMED
