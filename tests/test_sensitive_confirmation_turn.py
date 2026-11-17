"""Sensitive confirmation turn regression tests."""
import unittest
from unittest.mock import Mock
from sensitive_confirmation_turn import confirmation_turn


class ConfirmationTurnTests(unittest.TestCase):
    def setUp(self):
        self.evaluate = Mock(return_value=("session-2", "confirmed", "approved"))
        self.respond = Mock(return_value=None)
        self.dependencies = {name: Mock() for name in ("normalize", "record", "diagnostic_id", "log_error")}

    def run_turn(self, **overrides):
        args = dict(source="assist", satellite="kitchen", origin_device="device",
                    speaker="Jaco", evaluate=self.evaluate,
                    confirmation_response=self.respond, guest_commands={"guest"},
                    confirmations={"yes"}, **self.dependencies)
        args.update(overrides)
        return confirmation_turn("yes", "original", "session-1", **args)

    def test_confirmed_phrase(self):
        self.assertEqual(self.run_turn(), ("session-2", "approved", None, True))

    def test_confirmed_same_phrase_still_flagged(self):
        self.evaluate.return_value = ("session-2", "confirmed", "original")
        self.assertEqual(self.run_turn()[-1], True)

    def test_confirmation_response_short_circuits(self):
        self.respond.return_value = {"reply": "Please confirm"}
        self.assertEqual(self.run_turn(), ("session-2", "original", {"reply": "Please confirm"}, False))

    def test_pending_does_not_replace_phrase(self):
        self.evaluate.return_value = ("session-2", "pending", "other")
        self.assertEqual(self.run_turn()[1], "original")

    def test_non_assist_skips_evaluation(self):
        self.assertEqual(self.run_turn(source="browser"), ("session-1", "original", None, False))
        self.evaluate.assert_not_called()

    def test_non_assist_skips_response(self):
        self.run_turn(source="browser")
        self.respond.assert_not_called()

    def test_session_from_evaluator(self):
        self.assertEqual(self.run_turn()[0], "session-2")

    def test_speaker_forwarded(self):
        self.run_turn()
        self.assertEqual(self.evaluate.call_args.kwargs["speaker"], "Jaco")

    def test_source_forwarded_to_response(self):
        self.run_turn()
        self.assertEqual(self.respond.call_args.kwargs["source"], "assist")

    def test_record_callback_forwarded(self):
        self.run_turn()
        self.assertIs(self.respond.call_args.kwargs["record"], self.dependencies["record"])

    def test_evaluator_called_once(self):
        self.run_turn()
        self.evaluate.assert_called_once()
