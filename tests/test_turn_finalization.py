"""HTTP turn finalisation regression tests."""
import unittest
from declan.turn.turn_finalization import lighting_phrase_suggestion, apply_outcome_metadata
from declan.core.execution_results import Outcome


class TurnFinalizationTests(unittest.TestCase):
    def test_typed_and_legacy_outcomes_preserve_suggestion_gates(self):
        outcome: object
        for outcome in Outcome:
            with self.subTest(outcome=outcome):
                self.assertEqual(self.suggestion(outcome=outcome), self.suggestion(outcome=outcome.value))
        for outcome in ("future_outcome", [], None):
            self.assertIsNone(self.suggestion(outcome=outcome))

    def suggestion(self, *, previous=None, outcome="confirmed", actions=None,
                   scope="kitchen", message="turn off kitchen lights", now=120):
        if previous is None:
            previous = {"at": 100, "failed_light_phrase": {
                "text": "switch off kitchen lights", "scope": "kitchen",
                "actions": {"off"}}}
        return lighting_phrase_suggestion(previous, light_result=("Done", "confirmed"),
            outcome=outcome, actions={"off"} if actions is None else actions,
            scope=scope, message=message, now=now)

    def test_recent_corrected_lighting_phrase_suggested(self):
        self.assertEqual(self.suggestion(), "switch off kitchen lights")

    def test_stale_attempt_not_suggested(self):
        self.assertIsNone(self.suggestion(now=131))

    def test_unconfirmed_attempt_not_suggested(self):
        self.assertIsNone(self.suggestion(outcome="unresolved"))

    def test_different_action_not_suggested(self):
        self.assertIsNone(self.suggestion(actions={"on"}))

    def test_different_scope_not_suggested(self):
        self.assertIsNone(self.suggestion(scope="bedroom"))

    def test_identical_phrase_not_suggested(self):
        self.assertIsNone(self.suggestion(message="SWITCH OFF KITCHEN LIGHTS"))

    def test_no_previous_attempt_not_suggested(self):
        self.assertIsNone(lighting_phrase_suggestion(None, light_result=True,
            outcome="confirmed", actions={"off"}, scope="kitchen",
            message="turn off kitchen lights", now=120))

    def test_outcome_and_routine_status_attached(self):
        reply = {"reply": "Sorted."}
        self.assertIs(apply_outcome_metadata(reply, outcome="confirmed",
            routine_status={"status": "done"}), reply)
        self.assertEqual(reply["outcome"], "confirmed")
        self.assertEqual(reply["routine_status"], {"status": "done"})

    def test_missing_metadata_omitted(self):
        reply = {"reply": "Sorted."}
        apply_outcome_metadata(reply, outcome=None, routine_status=None)
        self.assertEqual(reply, {"reply": "Sorted."})
