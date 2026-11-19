"""Dispatch decisions remain enum-backed before response preparation."""
import unittest
from typing import Any

from execution_results import Outcome
from declan.turn.turn_dispatch_orchestration import DispatchResult


class DispatchOutcomeContractTests(unittest.TestCase):
    def result(self, **overrides):
        fields: dict[str, Any] = dict(reply="Observed", outcome=Outcome.CONFIRMED,
                      routine_status="Lights observed on", routine_turn=None,
                      routine_voice_result=None, lighting_context=None,
                      information_context=None, status_target=None, light_result=None)
        fields.update(overrides)
        return DispatchResult(**fields)

    def test_known_legacy_values_are_normalized_without_changing_meaning(self):
        for outcome in Outcome:
            with self.subTest(outcome=outcome):
                self.assertIs(self.result(outcome=outcome.value).outcome, outcome)
                self.assertIs(self.result(outcome=outcome).outcome, outcome)

    def test_unknown_outcomes_are_rejected_instead_of_becoming_success(self):
        outcome: object
        for outcome in ("ok", "success", "", "CONFIRMED", True, 1, {}):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                self.result(outcome=outcome)

    def test_unmatched_turn_remains_distinct_from_failed_execution(self):
        result = self.result(reply=None, outcome=None, routine_status=None)
        self.assertIsNone(result.outcome)
        self.assertIsNone(result.reply)
        self.assertIsNone(result.routine_status)

    def test_status_is_display_text_not_an_execution_enum(self):
        result = self.result(outcome=Outcome.UNVERIFIED,
                             routine_status="Accepted, completion has not been verified")
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(result.routine_status, "Accepted, completion has not been verified")
        for field in ("reply", "routine_status"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.result(**{field: {"unexpected": "metadata"}})
