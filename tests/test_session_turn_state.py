"""Session context and voice correction retry regression tests."""
import unittest
from session_turn_state import update_turn
from execution_results import Outcome


class SessionTurnStateTests(unittest.TestCase):
    def test_typed_and_legacy_outcomes_preserve_retry_state(self):
        for outcome in Outcome:
            with self.subTest(outcome=outcome):
                self.assertEqual(self.update(outcome=outcome, reply_text="Done.", light=True,
                    steps=[{"detail": "unresolved"}]), self.update(outcome=outcome.value,
                    reply_text="Done.", light=True, steps=[{"detail": "unresolved"}]))
        for outcome in ("future_outcome", []):
            self.assertFalse(self.update(outcome=outcome, reply_text="Done.")[2])
        self.assertTrue(self.update(outcome=None, reply_text="Done.")[2])

    def update(self, *, outcome="unresolved", reply_text="Unmatched", phrase="turn off kitchen",
               light=None, steps=None, scope="kitchen"):
        session = {"failed_light_phrase": {"old": True}}
        reply = {"reply": reply_text}
        success = update_turn(session, reply, message="turn off kitchen", phrase=phrase,
            outcome=outcome, scope=scope, status_target="light.kitchen",
            information_context=None, light_result=light,
            action_results=[] if steps is None else steps,
            actions={"off"}, unmatched_reply="Unmatched", now=123.0)
        return session, reply, success

    def test_unmatched_opens_voice_followup(self):
        session, reply, success = self.update()
        self.assertFalse(success)
        self.assertTrue(reply["continue_conversation"])
        self.assertEqual(reply["follow_up_timeout"], 10)
        self.assertEqual(session["pending_retry"], {
            "text": "turn off kitchen", "scope": "kitchen", "at": 123.0})

    def test_success_closes_followup(self):
        session, reply, success = self.update(outcome="confirmed", reply_text="Done.")
        self.assertTrue(success)
        self.assertFalse(reply["continue_conversation"])
        self.assertEqual(reply["follow_up_timeout"], 0)
        self.assertNotIn("pending_retry", session)

    def test_timer_success_counts_for_training(self):
        _, _, success = self.update(outcome="timer_set", reply_text="Timer set.")
        self.assertTrue(success)

    def test_unresolved_lighting_records_correction_context(self):
        session, _, _ = self.update(light=("Unknown.", "unresolved"),
            steps=[{"detail": "unresolved"}])
        self.assertEqual(session["failed_light_phrase"]["actions"], {"off"})
        self.assertEqual(session["device_status_scope"], "kitchen")

    def test_preview_does_not_store_failed_light_phrase(self):
        session, _, _ = self.update(phrase="preview turn off kitchen",
            light=("Unknown.", "unresolved"), steps=[{"detail": "unresolved"}])
        self.assertNotIn("failed_light_phrase", session)

    def test_missing_scope_never_stores_retry(self):
        session, reply, _ = self.update(scope=None)
        self.assertTrue(reply["continue_conversation"])
        self.assertNotIn("pending_retry", session)
