"""Lighting context finalization regression tests."""
import unittest
from lighting_context_finalization import confirmed_lighting_context
from execution_results import Outcome


class LightingContextFinalizationTests(unittest.TestCase):
    def test_typed_outcome_gate_matches_legacy_and_rejects_unknown_values(self):
        outcome: object
        for outcome in Outcome:
            self.assertEqual(self.context(outcome=outcome), self.context(outcome=outcome.value))
        for outcome in ("future_outcome", [], None):
            self.assertEqual(self.context(outcome=outcome), ())

    def context(self, phrase="turn on the lights", outcome="confirmed", scope="kitchen", steps=None):
        if steps is None:
            steps = [{"entity_id": "light.kitchen", "status": "confirmed"}]
        return confirmed_lighting_context(phrase, outcome, scope, steps)

    def test_confirmed_entity_retained(self):
        self.assertEqual(self.context(), ("light.kitchen",))

    def test_already_set_entity_retained(self):
        self.assertEqual(self.context(steps=[{"entity_id": "light.kitchen", "status": "already_set"}]),
                         ("light.kitchen",))

    def test_duplicate_entities_deduplicated_in_order(self):
        steps = [{"entity_id": "light.a", "status": "confirmed"},
                 {"entity_id": "light.b", "status": "already_set"},
                 {"entity_id": "light.a", "status": "confirmed"}]
        self.assertEqual(self.context(steps=steps), ("light.a", "light.b"))

    def test_failed_action_excluded(self):
        self.assertEqual(self.context(steps=[{"entity_id": "light.a", "status": "failed"}]), ())

    def test_missing_entity_excluded(self):
        self.assertEqual(self.context(steps=[{"status": "confirmed"}]), ())

    def test_unconfirmed_outcome_excluded(self):
        self.assertEqual(self.context(outcome="failed"), ())

    def test_unscoped_actions_excluded(self):
        self.assertEqual(self.context(scope=None), ())

    def test_two_hundred_actions_excluded(self):
        self.assertEqual(self.context(steps=[{"entity_id": "light.a", "status": "confirmed"}] * 200), ())

    def test_one_hundred_ninety_nine_actions_allowed(self):
        self.assertEqual(self.context(steps=[{"entity_id": "light.a", "status": "confirmed"}] * 199),
                         ("light.a",))

    def test_preview_excluded(self):
        self.assertEqual(self.context(phrase="preview turn on lights"), ())

    def test_dry_run_excluded(self):
        self.assertEqual(self.context(phrase="dry-run turn on lights"), ())

    def test_spaced_dry_run_excluded(self):
        self.assertEqual(self.context(phrase="dry run turn on lights"), ())

    def test_empty_actions(self):
        self.assertEqual(self.context(steps=[]), ())
