"""Voice confirmation decision and origin-binding tests."""
import unittest
from unittest.mock import Mock
from sensitive_confirmation_decision import evaluate


class SensitiveConfirmationDecisionTests(unittest.TestCase):
    def setUp(self):
        self.confirmations = Mock()
        self.confirmations.evaluate.return_value = ("continue", None)
        self.normalize = lambda message: message.lower().strip()

    def decide(self, message="assign guests", phrase="assign guests", session_id="session-1",
               satellite="assist_satellite.kitchen", origin_device="device-1", speaker="Jaco"):
        return evaluate(message, phrase, session_id, satellite=satellite,
                        origin_device=origin_device, speaker=speaker,
                        normalize=self.normalize, guest_commands={"assign guests": "assign"},
                        confirmations=self.confirmations,
                        new_session_id=lambda: "generated-session")

    def test_existing_session_preserved(self):
        self.assertEqual(self.decide()[0], "session-1")

    def test_missing_session_generated(self):
        self.assertEqual(self.decide(session_id=None)[0], "generated-session")

    def test_satellite_takes_precedence_over_device(self):
        self.decide()
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["origin"],
                         "assist_satellite.kitchen")

    def test_device_origin_fallback(self):
        self.decide(satellite=None)
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["origin"], "device-1")

    def test_unknown_origin_passed_through_for_denial(self):
        self.decide(satellite=None, origin_device=None)
        self.assertIsNone(self.confirmations.evaluate.call_args.kwargs["origin"])

    def test_yes_uses_original_spoken_confirmation(self):
        self.decide(message="YES", phrase="learned unrelated phrase")
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["phrase"], "yes")

    def test_no_uses_original_spoken_confirmation(self):
        self.decide(message="NO", phrase="learned unrelated phrase")
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["phrase"], "no")

    def test_non_confirmation_uses_resolved_phrase(self):
        self.decide(message="lights please", phrase="assign guests")
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["phrase"], "assign guests")

    def test_speaker_passed_to_confirmation_policy(self):
        self.decide(speaker="Edd")
        self.assertEqual(self.confirmations.evaluate.call_args.kwargs["speaker"], "Edd")

    def test_confirmed_phrase_returned(self):
        self.confirmations.evaluate.return_value = ("confirmed", "assign guests")
        self.assertEqual(self.decide()[1:], ("confirmed", "assign guests"))
