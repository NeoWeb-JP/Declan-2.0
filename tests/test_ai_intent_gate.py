import unittest
from ai_intent_gate import is_action_request


class IntentGateTests(unittest.TestCase):
    def test_device_requests(self):
        for utterance in ("turn on kitchen", "could you make the lounge brighter",
                          "please lower the blinds", "would you mind switching the lights off"):
            self.assertTrue(is_action_request(utterance))

    def test_unmatched_language_reaches_planning_without_a_verb_allowlist(self):
        for utterance in ("it's too dark in here", "I'm freezing", "the lounge is gloomy",
                          "can you sort the lights", "tell me a joke", "how are you"):
            self.assertTrue(is_action_request(utterance))

    def test_invalid_or_oversized_input_is_not_eligible(self):
        for utterance in (None, 42, "", " \t\n", "x" * 1001):
            self.assertFalse(is_action_request(utterance))


if __name__ == "__main__":
    unittest.main()
