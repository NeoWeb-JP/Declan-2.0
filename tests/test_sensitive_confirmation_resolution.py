"""Sensitive confirmation phrase resolution regressions."""

import unittest
from types import SimpleNamespace

from sensitive_confirmation_resolution import resolved_confirmation


class SensitiveConfirmationResolutionTests(unittest.TestCase):
    def test_confirmed_phrase_replaces_original_and_effective_message(self):
        result = SimpleNamespace(
            confirmed=True, phrase="turn on lounge lights",
            session_id="new-session", reply=None,
        )
        self.assertEqual(
            resolved_confirmation(result, "yes", "yes"),
            ("new-session", "turn on lounge lights", "turn on lounge lights", None),
        )

    def test_unconfirmed_phrase_keeps_original_and_effective_message(self):
        result = SimpleNamespace(
            confirmed=False, phrase="ignored", session_id="same-session",
            reply={"reply": "Please confirm"},
        )
        self.assertEqual(
            resolved_confirmation(result, "original", "normalized"),
            ("same-session", "original", "normalized", {"reply": "Please confirm"}),
        )

    def test_confirmation_without_reply_does_not_change_unconfirmed_phrase(self):
        result = SimpleNamespace(
            confirmed=False, phrase="ignored", session_id="s", reply=None,
        )
        self.assertEqual(
            resolved_confirmation(result, "stop", "stop"),
            ("s", "stop", "stop", None),
        )


if __name__ == "__main__":
    unittest.main()
