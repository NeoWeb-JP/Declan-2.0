import unittest
from ai_intent_gate import is_action_request


class IntentGateTests(unittest.TestCase):
    def test_device_requests(self):
        for utterance in ("turn on kitchen", "could you make the lounge brighter",
                          "please lower the blinds", "would you mind switching the lights off"):
            self.assertTrue(is_action_request(utterance))

    def test_general_chat_not_intercepted(self):
        for utterance in ("tell me a joke", "what's the weather", "how are you"):
            self.assertFalse(is_action_request(utterance))


if __name__ == "__main__":
    unittest.main()
